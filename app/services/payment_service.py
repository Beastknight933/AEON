import datetime
import decimal
import uuid
from typing import Any, Dict, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    AuditAction,
    PaymentStatus,
    PurchaseStatus,
    ReservationStatus,
    TransactionStatus,
    TransactionType,
)
from app.core.errors import NotFoundError, PaymentError, StateTransitionError
from app.core.logging import get_logger
from app.integrations.paypal.client import paypal_client
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
    def __init__(self, session: AsyncSession):
        self.session = session
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
        order_res = await paypal_client.create_order(
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

        if attempt.status not in (PaymentStatus.ORDER_CREATED, PaymentStatus.BUYER_APPROVAL_PENDING):
            raise StateTransitionError(
                current_state=attempt.status.value,
                attempted_state=PaymentStatus.COMPLETED.value,
                entity="PaymentAttempt",
            )

        attempt.status = PaymentStatus.CAPTURE_PENDING
        await self.session.flush()

        capture_idempotency_key = f"aeon_cap_{attempt.id}_{uuid.uuid4().hex[:6]}"
        capture_res = await paypal_client.capture_order(
            order_id=provider_order_id,
            idempotency_key=capture_idempotency_key,
        )

        now = datetime.datetime.now(datetime.timezone.utc)
        if capture_res.status == "COMPLETED":
            attempt.status = PaymentStatus.COMPLETED
            attempt.provider_capture_id = capture_res.id

            # Settle budget reservation atomically
            reservation = await self.budget_repo.get_reservation_by_purchase(pr.id)
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
        else:
            attempt.status = PaymentStatus.FAILED
            attempt.error_message = f"PayPal capture returned status: {capture_res.status}"

            # Release reserved funds on failure
            reservation = await self.budget_repo.get_reservation_by_purchase(pr.id)
            if reservation and reservation.status == ReservationStatus.ACTIVE:
                await self.budget_repo.release_reservation_atomic(reservation.id)

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
        # 1. Verify authenticity
        await PayPalWebhookVerifier.verify(headers, event_body)

        event_id = event_body.get("id") or str(uuid.uuid4())
        event_type = event_body.get("event_type", "UNKNOWN")

        # 2. Enforce idempotency: Has this provider event ID already been recorded?
        stmt = select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
        existing_wh = await self.session.scalar(stmt)
        if existing_wh and existing_wh.is_processed:
            logger.info(f"PayPal webhook {event_id} already processed. Skipping duplicate.")
            return {"status": "already_processed", "event_id": event_id}

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

        # 3. Process event types
        resource = event_body.get("resource", {})
        if event_type == "CHECKOUT.ORDER.APPROVED":
            order_id = resource.get("id")
            if order_id:
                stmt_att = select(PaymentAttempt).where(PaymentAttempt.provider_order_id == order_id)
                attempt = await self.session.scalar(stmt_att)
                if attempt and attempt.status == PaymentStatus.ORDER_CREATED:
                    attempt.status = PaymentStatus.BUYER_APPROVAL_PENDING

        elif event_type == "PAYMENT.CAPTURE.COMPLETED":
            capture_id = resource.get("id")
            order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
            if order_id:
                stmt_att = select(PaymentAttempt).where(PaymentAttempt.provider_order_id == order_id)
                attempt = await self.session.scalar(stmt_att)
                if attempt and attempt.status != PaymentStatus.COMPLETED:
                    attempt.status = PaymentStatus.COMPLETED
                    attempt.provider_capture_id = capture_id
                    pr = await self.session.scalar(
                        select(PurchaseRequest).where(PurchaseRequest.id == attempt.purchase_request_id)
                    )
                    if pr:
                        pr.status = PurchaseStatus.COMPLETED
                        res = await self.budget_repo.get_reservation_by_purchase(pr.id)
                        budget_id = None
                        if res and res.status == ReservationStatus.ACTIVE:
                            await self.budget_repo.settle_reservation_atomic(res.id)
                            budget_id = res.budget_id

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

        elif event_type in ("PAYMENT.CAPTURE.DENIED", "PAYMENT.CAPTURE.FAILED"):
            order_id = resource.get("supplementary_data", {}).get("related_ids", {}).get("order_id")
            if order_id:
                stmt_att = select(PaymentAttempt).where(PaymentAttempt.provider_order_id == order_id)
                attempt = await self.session.scalar(stmt_att)
                if attempt and attempt.status != PaymentStatus.FAILED:
                    attempt.status = PaymentStatus.FAILED
                    res = await self.budget_repo.get_reservation_by_purchase(attempt.purchase_request_id)
                    if res and res.status == ReservationStatus.ACTIVE:
                        await self.budget_repo.release_reservation_atomic(res.id)

        elif event_type == "PAYMENT.CAPTURE.REFUNDED":
            parent_capture_id = resource.get("links", [{}])[0].get("href", "").split("/")[-1]
            amount_val = decimal.Decimal(resource.get("amount", {}).get("value", "0.00"))
            currency_val = resource.get("amount", {}).get("currency_code", "USD")
            stmt_tx = select(Transaction).where(
                Transaction.provider_transaction_id == parent_capture_id,
                Transaction.type == TransactionType.PURCHASE,
            )
            orig_tx = await self.session.scalar(stmt_tx)
            if orig_tx:
                # Record refund transaction without deleting the original
                refund_tx = Transaction(
                    organization_id=orig_tx.organization_id,
                    purchase_request_id=orig_tx.purchase_request_id,
                    budget_id=orig_tx.budget_id,
                    type=TransactionType.REFUND,
                    status=TransactionStatus.REFUNDED,
                    amount=amount_val,
                    currency=currency_val,
                    provider_transaction_id=resource.get("id"),
                )
                self.session.add(refund_tx)
                if orig_tx.budget_id:
                    await self.budget_repo.record_refund_atomic(orig_tx.budget_id, amount_val)

        existing_wh.is_processed = True
        existing_wh.processed_at = datetime.datetime.now(datetime.timezone.utc)
        await self.session.commit()

        return {"status": "processed", "event_id": event_id, "event_type": event_type}
