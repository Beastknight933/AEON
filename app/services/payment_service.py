import datetime
import decimal
import uuid
from typing import Any, Dict, List, Optional
import httpx
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    AuditAction,
    FulfillmentStatus,
    PaymentStatus,
    PurchaseStatus,
    ReservationStatus,
    TransactionStatus,
    TransactionType,
)
from app.core.errors import NotFoundError, PaymentError, StateTransitionError
from app.core.logging import get_logger
from app.integrations.paypal.client import BasePayPalClient, get_paypal_client
from app.integrations.paypal.webhook_verifier import PayPalWebhookVerifier
from app.models.audit import AuditEvent
from app.models.payment import PaymentAttempt
from app.models.purchase import PurchaseRequest
from app.models.supplier import SupplierQuote
from app.models.transaction import Transaction
from app.models.webhook import WebhookEvent
from app.repositories.budget_repo import BudgetRepository
from app.schemas.payment import (
    PaymentCaptureResponse,
    PaymentOrderCreateResponse,
    PaymentStatusResponse,
)

logger = get_logger("aeon.payment_service")


class PaymentService:
    def __init__(self, session: AsyncSession, client: Optional[BasePayPalClient] = None):
        self.session = session
        self.client = client or get_paypal_client()
        self.budget_repo = BudgetRepository(session)

    async def create_payment_order(
        self, purchase_request_id: uuid.UUID, organization_id: uuid.UUID
    ) -> PaymentOrderCreateResponse:
        stmt = (
            select(PurchaseRequest)
            .options(selectinload(PurchaseRequest.quotes))
            .where(
                PurchaseRequest.id == purchase_request_id,
                PurchaseRequest.organization_id == organization_id,
            )
        )
        pr = await self.session.scalar(stmt)
        if not pr:
            raise NotFoundError("PurchaseRequest", purchase_request_id)

        # Enforce: Only AUTHORIZED purchases may proceed to payment order creation
        if pr.status != PurchaseStatus.AUTHORIZED:
            raise StateTransitionError(
                current_state=pr.status.value,
                attempted_state="CREATE_PAYMENT_ORDER",
                entity="PurchaseRequest",
            )

        if not pr.selected_quote_id:
            raise PaymentError("No selected supplier quote attached to this purchase.")

        # Find selected quote
        quote = next((q for q in pr.quotes if q.id == pr.selected_quote_id), None)
        if not quote:
            stmt_q = select(SupplierQuote).where(SupplierQuote.id == pr.selected_quote_id)
            quote = await self.session.scalar(stmt_q)
            if not quote:
                raise NotFoundError("SupplierQuote", pr.selected_quote_id)

        # Verify active budget reservation
        reservation = await self.budget_repo.get_reservation_by_purchase(pr.id)
        if not reservation or reservation.status != ReservationStatus.ACTIVE:
            raise PaymentError("No active budget reservation found for this purchase.")

        # Check existing active payment attempt for idempotency
        stmt_attempt = (
            select(PaymentAttempt)
            .where(
                PaymentAttempt.purchase_request_id == pr.id,
                PaymentAttempt.status.in_([PaymentStatus.ORDER_CREATED, PaymentStatus.BUYER_APPROVAL_PENDING]),
            )
            .order_by(PaymentAttempt.created_at.desc())
            .limit(1)
        )
        existing_attempt = await self.session.scalar(stmt_attempt)
        if existing_attempt and existing_attempt.provider_order_id:
            return PaymentOrderCreateResponse(
                payment_attempt_id=existing_attempt.id,
                purchase_request_id=pr.id,
                provider_order_id=existing_attempt.provider_order_id,
                amount=existing_attempt.amount,
                currency=existing_attempt.currency,
                status=existing_attempt.status,
                approval_url=existing_attempt.approval_url,
                created_at=existing_attempt.created_at,
            )

        idempotency_key = f"aeon_order_{pr.id}_{uuid.uuid4().hex[:8]}"
        order_res = await self.client.create_order(
            purchase_id=pr.id,
            amount=quote.total_amount,
            currency=quote.currency,
            idempotency_key=idempotency_key,
        )

        approval_link = next((link.href for link in order_res.links if link.rel == "approve"), None)

        attempt = PaymentAttempt(
            purchase_request_id=pr.id,
            provider="paypal",
            status=PaymentStatus.ORDER_CREATED,
            amount=quote.total_amount,
            currency=quote.currency,
            provider_order_id=order_res.id,
            idempotency_key=idempotency_key,
            approval_url=approval_link,
        )
        self.session.add(attempt)

        self.session.add(
            AuditEvent(
                organization_id=organization_id,
                actor_type="SYSTEM",
                actor_id="paypal_service",
                action=AuditAction.PAYMENT_ORDER_CREATED.value,
                entity_type="payment_attempt",
                entity_id=order_res.id,
                metadata_json={"order_id": order_res.id, "amount": str(quote.total_amount)},
            )
        )

        await self.session.commit()
        await self.session.refresh(attempt)

        return PaymentOrderCreateResponse(
            payment_attempt_id=attempt.id,
            purchase_request_id=pr.id,
            provider_order_id=order_res.id,
            amount=attempt.amount,
            currency=attempt.currency,
            status=attempt.status,
            approval_url=approval_link,
            created_at=attempt.created_at,
        )

    async def capture_payment(
        self, provider_order_id: str, organization_id: uuid.UUID
    ) -> PaymentCaptureResponse:
        stmt = (
            select(PaymentAttempt)
            .options(selectinload(PaymentAttempt.purchase_request))
            .where(PaymentAttempt.provider_order_id == provider_order_id)
        )
        attempt = await self.session.scalar(stmt)
        if not attempt:
            raise NotFoundError("PaymentAttempt with Order ID", provider_order_id)

        pr = attempt.purchase_request
        if not pr or pr.organization_id != organization_id:
            raise NotFoundError("PaymentAttempt", provider_order_id)

        # Idempotent: If already completed, return existing completion state
        if attempt.status == PaymentStatus.COMPLETED:
            stmt_tx = select(Transaction).where(
                Transaction.purchase_request_id == pr.id,
                Transaction.provider_transaction_id == attempt.provider_capture_id,
            )
            tx = await self.session.scalar(stmt_tx)
            return PaymentCaptureResponse(
                payment_attempt_id=attempt.id,
                purchase_request_id=pr.id,
                provider_capture_id=attempt.provider_capture_id or "",
                amount=attempt.amount,
                currency=attempt.currency,
                status=attempt.status,
                transaction_id=tx.id if tx else None,
                completed_at=attempt.updated_at,
            )

        if attempt.status not in (
            PaymentStatus.ORDER_CREATED,
            PaymentStatus.BUYER_APPROVAL_PENDING,
            PaymentStatus.CAPTURE_PENDING,
        ):
            raise StateTransitionError(
                current_state=attempt.status.value,
                attempted_state=PaymentStatus.COMPLETED.value,
                entity="PaymentAttempt",
            )

        # Verify active budget reservation
        reservation = await self.budget_repo.get_reservation_by_purchase(pr.id)
        if not reservation or reservation.status != ReservationStatus.ACTIVE:
            raise PaymentError("No active budget reservation found for this purchase.")

        attempt.status = PaymentStatus.CAPTURE_PENDING
        await self.session.flush()

        capture_idempotency_key = f"aeon_cap_{attempt.id}_{uuid.uuid4().hex[:6]}"

        try:
            capture_res = await self.client.capture_order(
                order_id=provider_order_id,
                idempotency_key=capture_idempotency_key,
            )
        except (httpx.TimeoutException, httpx.RequestError, TimeoutError) as exc:
            # UNCERTAIN OUTCOME: Network timeout / connection error.
            # Do NOT mark complete, and do NOT release reserved budget funds.
            attempt.status = PaymentStatus.CAPTURE_PENDING
            attempt.error_message = f"Capture outcome uncertain due to network exception: {str(exc)}"
            self.session.add(
                AuditEvent(
                    organization_id=organization_id,
                    actor_type="SYSTEM",
                    actor_id="paypal_service",
                    action=AuditAction.PAYMENT_FAILED.value,
                    entity_type="payment_attempt",
                    entity_id=provider_order_id,
                    metadata_json={"error": attempt.error_message, "uncertain": True},
                )
            )
            await self.session.commit()
            raise PaymentError(
                f"Payment capture timed out or network error encountered. "
                f"Outcome is uncertain; budget reservation is retained pending reconciliation. Details: {exc}"
            )

        now = datetime.datetime.now(datetime.timezone.utc)
        if capture_res.status == "COMPLETED":
            attempt.status = PaymentStatus.COMPLETED
            attempt.provider_capture_id = capture_res.id

            # Settle budget reservation atomically
            budget_id = None
            if reservation and reservation.status == ReservationStatus.ACTIVE:
                await self.budget_repo.settle_reservation_atomic(reservation.id)
                budget_id = reservation.budget_id

            # Create immutable ledger transaction
            tx = Transaction(
                organization_id=organization_id,
                purchase_request_id=pr.id,
                budget_id=budget_id,
                type=TransactionType.PURCHASE,
                status=TransactionStatus.SETTLED,
                amount=attempt.amount,
                currency=attempt.currency,
                provider_transaction_id=capture_res.id,
            )
            self.session.add(tx)

            # Purchase lifecycle: COMPLETED
            pr.status = PurchaseStatus.COMPLETED
            pr.fulfillment_status = FulfillmentStatus.PENDING

            self.session.add(
                AuditEvent(
                    organization_id=organization_id,
                    actor_type="SYSTEM",
                    actor_id="paypal_service",
                    action=AuditAction.PAYMENT_CAPTURED.value,
                    entity_type="transaction",
                    entity_id=capture_res.id,
                    metadata_json={"capture_id": capture_res.id, "amount": str(attempt.amount)},
                )
            )

            await self.session.commit()
            await self.session.refresh(attempt)
            await self.session.refresh(tx)

            return PaymentCaptureResponse(
                payment_attempt_id=attempt.id,
                purchase_request_id=pr.id,
                provider_capture_id=capture_res.id,
                amount=attempt.amount,
                currency=attempt.currency,
                status=attempt.status,
                transaction_id=tx.id,
                completed_at=now,
            )
        elif capture_res.status in ("PENDING", "ACTION_REQUIRED"):
            # Pending processing - retain reservation
            attempt.status = PaymentStatus.CAPTURE_PENDING
            attempt.error_message = f"PayPal capture is pending (status: {capture_res.status})"
            await self.session.commit()
            raise PaymentError(f"PayPal capture is pending (status: {capture_res.status}). Reservation retained.")
        else:
            # Definitive terminal failure: DECLINED, FAILED, VOIDED
            attempt.status = PaymentStatus.FAILED
            attempt.error_message = f"PayPal capture returned terminal status: {capture_res.status}"

            # Release reserved funds on definitive failure
            if reservation and reservation.status == ReservationStatus.ACTIVE:
                await self.budget_repo.release_reservation_atomic(reservation.id)

            pr.status = PurchaseStatus.CANCELLED
            pr.fulfillment_status = FulfillmentStatus.FAILED

            self.session.add(
                AuditEvent(
                    organization_id=organization_id,
                    actor_type="SYSTEM",
                    actor_id="paypal_service",
                    action=AuditAction.PAYMENT_FAILED.value,
                    entity_type="payment_attempt",
                    entity_id=provider_order_id,
                    metadata_json={"error": attempt.error_message},
                )
            )
            await self.session.commit()
            raise PaymentError(f"PayPal capture failed: {capture_res.status}")

    async def get_payment_status(
        self, provider_order_id: str, organization_id: uuid.UUID
    ) -> PaymentStatusResponse:
        stmt = (
            select(PaymentAttempt)
            .join(PurchaseRequest, PaymentAttempt.purchase_request_id == PurchaseRequest.id)
            .where(
                PaymentAttempt.provider_order_id == provider_order_id,
                PurchaseRequest.organization_id == organization_id,
            )
        )
        attempt = await self.session.scalar(stmt)
        if not attempt:
            raise NotFoundError("PaymentAttempt", provider_order_id)
        return PaymentStatusResponse.model_validate(attempt)

    async def process_paypal_webhook(
        self, headers: Dict[str, str], event_body: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Verify authenticity, enforce unique provider event IDs, handle duplicate,
        delayed, and out-of-order webhook events, update transaction ledger,
        settle or release budget reservations, and record audit trails.
        """
        # 1. Verify authenticity using PayPal's verification mechanism
        await PayPalWebhookVerifier.verify(headers, event_body)

        event_id = event_body.get("id") or str(uuid.uuid4())
        event_type = event_body.get("event_type", "UNKNOWN")

        # 2. Enforce idempotency: Has this provider event ID already been recorded?
        stmt = select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
        existing_wh = await self.session.scalar(stmt)
        if existing_wh and existing_wh.is_processed:
            logger.info(f"PayPal webhook {event_id} ({event_type}) already processed. Skipping duplicate.")
            return {"status": "already_processed", "event_id": event_id, "event_type": event_type}

        if not existing_wh:
            existing_wh = WebhookEvent(
                provider="paypal",
                provider_event_id=event_id,
                event_type=event_type,
                payload=event_body,
                is_processed=False,
            )
            self.session.add(existing_wh)
            await self.session.flush()

        resource = event_body.get("resource", {})

        # Record audit event for webhook receipt (organization_id=None respects PostgreSQL nullable FK)
        self.session.add(
            AuditEvent(
                organization_id=None,
                actor_type="WEBHOOK",
                actor_id="paypal",
                action=AuditAction.WEBHOOK_RECEIVED.value,
                entity_type="webhook_event",
                entity_id=event_id,
                metadata_json={"event_type": event_type, "event_id": event_id},
            )
        )

        # 3. Process event types with delayed/out-of-order handling
        if event_type == "CHECKOUT.ORDER.APPROVED":
            order_id = resource.get("id")
            if order_id:
                stmt_att = select(PaymentAttempt).where(PaymentAttempt.provider_order_id == order_id)
                attempt = await self.session.scalar(stmt_att)
                # Out-of-order check: do not regress state if already in capture or completed
                if attempt and attempt.status == PaymentStatus.ORDER_CREATED:
                    attempt.status = PaymentStatus.BUYER_APPROVAL_PENDING
                    logger.info(f"Order {order_id} transitioned to BUYER_APPROVAL_PENDING via webhook.")

        elif event_type == "PAYMENT.CAPTURE.COMPLETED":
            capture_id = resource.get("id")
            order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
            stmt_att = select(PaymentAttempt).where(
                (PaymentAttempt.provider_order_id == order_id) | (PaymentAttempt.provider_capture_id == capture_id)
            )
            attempt = await self.session.scalar(stmt_att)
            if attempt and attempt.status != PaymentStatus.COMPLETED:
                attempt.status = PaymentStatus.COMPLETED
                attempt.provider_capture_id = capture_id
                pr = await self.session.scalar(
                    select(PurchaseRequest).where(PurchaseRequest.id == attempt.purchase_request_id)
                )
                if pr:
                    pr.status = PurchaseStatus.COMPLETED
                    pr.fulfillment_status = FulfillmentStatus.PENDING

                    res = await self.budget_repo.get_reservation_by_purchase(pr.id)
                    budget_id = None
                    if res and res.status == ReservationStatus.ACTIVE:
                        await self.budget_repo.settle_reservation_atomic(res.id)
                        budget_id = res.budget_id

                    stmt_tx = select(Transaction).where(
                        Transaction.purchase_request_id == pr.id,
                        Transaction.provider_transaction_id == capture_id,
                    )
                    existing_tx = await self.session.scalar(stmt_tx)
                    if not existing_tx:
                        tx = Transaction(
                            organization_id=pr.organization_id,
                            purchase_request_id=pr.id,
                            budget_id=budget_id,
                            type=TransactionType.PURCHASE,
                            status=TransactionStatus.SETTLED,
                            amount=attempt.amount,
                            currency=attempt.currency,
                            provider_transaction_id=capture_id,
                        )
                        self.session.add(tx)

                    self.session.add(
                        AuditEvent(
                            organization_id=pr.organization_id,
                            actor_type="WEBHOOK",
                            actor_id="paypal",
                            action=AuditAction.PAYMENT_CAPTURED.value,
                            entity_type="transaction",
                            entity_id=capture_id,
                            metadata_json={"capture_id": capture_id, "amount": str(attempt.amount)},
                        )
                    )

        elif event_type == "PAYMENT.CAPTURE.PENDING":
            capture_id = resource.get("id")
            order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
            stmt_att = select(PaymentAttempt).where(
                (PaymentAttempt.provider_order_id == order_id) | (PaymentAttempt.provider_capture_id == capture_id)
            )
            attempt = await self.session.scalar(stmt_att)
            if attempt and attempt.status != PaymentStatus.COMPLETED:
                attempt.status = PaymentStatus.CAPTURE_PENDING
                attempt.provider_capture_id = capture_id
                # Reservation is retained pending clearing!

        elif event_type in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.FAILED"):
            order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
            capture_id = resource.get("id")
            stmt_att = select(PaymentAttempt).where(
                (PaymentAttempt.provider_order_id == order_id) | (PaymentAttempt.provider_capture_id == capture_id)
            )
            attempt = await self.session.scalar(stmt_att)
            if attempt:
                # Out-of-order check: do NOT fail an already COMPLETED payment
                if attempt.status == PaymentStatus.COMPLETED:
                    logger.warning(f"Ignoring denial {event_type} for already COMPLETED attempt {attempt.id}")
                elif attempt.status != PaymentStatus.FAILED:
                    attempt.status = PaymentStatus.FAILED
                    attempt.error_message = f"PayPal capture failed: {event_type}"
                    pr = await self.session.scalar(
                        select(PurchaseRequest).where(PurchaseRequest.id == attempt.purchase_request_id)
                    )
                    if pr:
                        pr.status = PurchaseStatus.CANCELLED
                        pr.fulfillment_status = FulfillmentStatus.FAILED
                        res = await self.budget_repo.get_reservation_by_purchase(pr.id)
                        if res and res.status == ReservationStatus.ACTIVE:
                            await self.budget_repo.release_reservation_atomic(res.id)

                        self.session.add(
                            AuditEvent(
                                organization_id=pr.organization_id,
                                actor_type="WEBHOOK",
                                actor_id="paypal",
                                action=AuditAction.PAYMENT_FAILED.value,
                                entity_type="payment_attempt",
                                entity_id=attempt.provider_order_id or str(attempt.id),
                                metadata_json={"error": attempt.error_message},
                            )
                        )

        elif event_type == "PAYMENT.CAPTURE.REFUNDED":
            # Extract parent capture id
            parent_capture_id = None
            for link in resource.get("links", []):
                if link.get("rel") == "up":
                    parent_capture_id = link.get("href", "").rstrip("/").split("/")[-1]
                    break
            if not parent_capture_id:
                parent_capture_id = (
                    resource.get("parent_payment")
                    or resource.get("supplementary_data", {}).get("related_ids", {}).get("capture_id")
                )

            amount_val = decimal.Decimal(resource.get("amount", {}).get("value", "0.00"))
            currency_val = resource.get("amount", {}).get("currency_code", "USD")
            refund_id = resource.get("id") or str(uuid.uuid4())

            stmt_tx = select(Transaction).where(
                Transaction.provider_transaction_id == parent_capture_id,
                Transaction.type == TransactionType.PURCHASE,
            )
            orig_tx = await self.session.scalar(stmt_tx)
            if orig_tx:
                # Idempotency check: has this refund already been ledgered?
                stmt_dup = select(Transaction).where(
                    Transaction.provider_transaction_id == refund_id,
                    Transaction.type == TransactionType.REFUND,
                )
                existing_refund = await self.session.scalar(stmt_dup)
                if not existing_refund:
                    refund_tx = Transaction(
                        organization_id=orig_tx.organization_id,
                        purchase_request_id=orig_tx.purchase_request_id,
                        budget_id=orig_tx.budget_id,
                        type=TransactionType.REFUND,
                        status=TransactionStatus.REFUNDED,
                        amount=amount_val,
                        currency=currency_val,
                        provider_transaction_id=refund_id,
                    )
                    self.session.add(refund_tx)

                    # Update attempt status
                    stmt_att = select(PaymentAttempt).where(
                        PaymentAttempt.purchase_request_id == orig_tx.purchase_request_id
                    )
                    attempt = await self.session.scalar(stmt_att)
                    if attempt:
                        attempt.status = PaymentStatus.REFUNDED

                    if orig_tx.budget_id:
                        await self.budget_repo.record_refund_atomic(orig_tx.budget_id, amount_val)

                    self.session.add(
                        AuditEvent(
                            organization_id=orig_tx.organization_id,
                            actor_type="WEBHOOK",
                            actor_id="paypal",
                            action=AuditAction.PAYMENT_REFUNDED.value,
                            entity_type="transaction",
                            entity_id=refund_id,
                            metadata_json={
                                "refund_id": refund_id,
                                "parent_capture_id": parent_capture_id,
                                "amount": str(amount_val),
                            },
                        )
                    )

        existing_wh.is_processed = True
        existing_wh.processed_at = datetime.datetime.now(datetime.timezone.utc)
        await self.session.commit()

        return {"status": "processed", "event_id": event_id, "event_type": event_type}

    async def reconcile_payment(
        self, provider_order_id: str, organization_id: uuid.UUID
    ) -> PaymentStatusResponse:
        """
        Reconcile uncertain or pending payments against PayPal's authoritative API.
        Enforces state transition rules, settles or releases budget reservations,
        and logs audit events based on PayPal's authoritative ground truth.
        """
        stmt = (
            select(PaymentAttempt)
            .options(selectinload(PaymentAttempt.purchase_request))
            .join(PurchaseRequest, PaymentAttempt.purchase_request_id == PurchaseRequest.id)
            .where(
                PaymentAttempt.provider_order_id == provider_order_id,
                PurchaseRequest.organization_id == organization_id,
            )
        )
        attempt = await self.session.scalar(stmt)
        if not attempt:
            raise NotFoundError("PaymentAttempt", provider_order_id)

        pr = attempt.purchase_request
        # If already COMPLETED and transaction exists, return immediately
        if attempt.status == PaymentStatus.COMPLETED:
            return PaymentStatusResponse.model_validate(attempt)

        # Query PayPal's authoritative API
        order_data = await self.client.get_order(provider_order_id)
        authoritative_status = order_data.get("status", "UNKNOWN")

        # Extract any capture information
        captures = []
        for pu in order_data.get("purchase_units", []):
            for cap in pu.get("payments", {}).get("captures", []):
                captures.append(cap)

        now = datetime.datetime.now(datetime.timezone.utc)
        reservation = await self.budget_repo.get_reservation_by_purchase(pr.id)

        if authoritative_status == "COMPLETED" or any(c.get("status") == "COMPLETED" for c in captures):
            # Authoritative settlement on PayPal side
            cap_id = captures[0].get("id") if captures else f"RECON-{provider_order_id}"
            attempt.status = PaymentStatus.COMPLETED
            attempt.provider_capture_id = cap_id
            attempt.error_message = None

            budget_id = None
            if reservation and reservation.status == ReservationStatus.ACTIVE:
                await self.budget_repo.settle_reservation_atomic(reservation.id)
                budget_id = reservation.budget_id

            # Ensure transaction is recorded
            stmt_tx = select(Transaction).where(
                Transaction.purchase_request_id == pr.id,
                Transaction.type == TransactionType.PURCHASE,
            )
            tx = await self.session.scalar(stmt_tx)
            if not tx:
                tx = Transaction(
                    organization_id=organization_id,
                    purchase_request_id=pr.id,
                    budget_id=budget_id,
                    type=TransactionType.PURCHASE,
                    status=TransactionStatus.SETTLED,
                    amount=attempt.amount,
                    currency=attempt.currency,
                    provider_transaction_id=cap_id,
                )
                self.session.add(tx)

            pr.status = PurchaseStatus.COMPLETED
            pr.fulfillment_status = FulfillmentStatus.PENDING

            self.session.add(
                AuditEvent(
                    organization_id=organization_id,
                    actor_type="SYSTEM",
                    actor_id="reconciliation_service",
                    action=AuditAction.RECONCILIATION_PERFORMED.value,
                    entity_type="payment_attempt",
                    entity_id=provider_order_id,
                    metadata_json={
                        "reconciled_status": "COMPLETED",
                        "provider_capture_id": cap_id,
                        "authoritative_status": authoritative_status,
                    },
                )
            )

        elif authoritative_status in ("VOIDED", "EXPIRED") or any(c.get("status") in ("DECLINED", "FAILED") for c in captures):
            # Authoritative definitive failure on PayPal side
            attempt.status = PaymentStatus.FAILED
            attempt.error_message = f"Authoritative reconciliation: order is {authoritative_status}"

            if reservation and reservation.status == ReservationStatus.ACTIVE:
                await self.budget_repo.release_reservation_atomic(reservation.id)

            pr.status = PurchaseStatus.CANCELLED
            pr.fulfillment_status = FulfillmentStatus.FAILED

            self.session.add(
                AuditEvent(
                    organization_id=organization_id,
                    actor_type="SYSTEM",
                    actor_id="reconciliation_service",
                    action=AuditAction.RECONCILIATION_PERFORMED.value,
                    entity_type="payment_attempt",
                    entity_id=provider_order_id,
                    metadata_json={
                        "reconciled_status": "FAILED",
                        "authoritative_status": authoritative_status,
                    },
                )
            )

        elif authoritative_status == "APPROVED":
            attempt.status = PaymentStatus.BUYER_APPROVAL_PENDING
            self.session.add(
                AuditEvent(
                    organization_id=organization_id,
                    actor_type="SYSTEM",
                    actor_id="reconciliation_service",
                    action=AuditAction.RECONCILIATION_PERFORMED.value,
                    entity_type="payment_attempt",
                    entity_id=provider_order_id,
                    metadata_json={"reconciled_status": "BUYER_APPROVAL_PENDING"},
                )
            )

        elif any(c.get("status") == "PENDING" for c in captures) or authoritative_status == "PAYER_ACTION_REQUIRED":
            attempt.status = PaymentStatus.CAPTURE_PENDING

        await self.session.commit()
        await self.session.refresh(attempt)
        return PaymentStatusResponse.model_validate(attempt)

    async def reconcile_pending_payments(
        self, organization_id: uuid.UUID
    ) -> List[PaymentStatusResponse]:
        """
        Reconcile all in-flight or uncertain payment attempts for an organization.
        """
        stmt = (
            select(PaymentAttempt.provider_order_id)
            .join(PurchaseRequest, PaymentAttempt.purchase_request_id == PurchaseRequest.id)
            .where(
                PurchaseRequest.organization_id == organization_id,
                PaymentAttempt.status.in_([
                    PaymentStatus.CAPTURE_PENDING,
                    PaymentStatus.BUYER_APPROVAL_PENDING,
                    PaymentStatus.ORDER_CREATED,
                ]),
                PaymentAttempt.provider_order_id.isnot(None),
            )
        )
        order_ids = (await self.session.scalars(stmt)).all()
        results = []
        for oid in order_ids:
            if oid:
                res = await self.reconcile_payment(oid, organization_id)
                results.append(res)
        return results
