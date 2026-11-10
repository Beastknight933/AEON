import datetime
import decimal
import math
import uuid
from typing import Any, Dict, List, Optional
from sqlalchemy import func, or_, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TransactionStatus, TransactionType
from app.core.errors import NotFoundError
from app.models.audit import AuditEvent
from app.models.payment import PaymentAttempt
from app.models.purchase import PurchaseRequest
from app.models.transaction import Transaction
from app.schemas.common import PaginatedResponse
from app.schemas.transaction import (
    PaymentAttemptSummaryForTransaction,
    PurchaseSummaryForTransaction,
    ReconciliationResponse,
    TimelineEventItem,
    TransactionDetailResponse,
    TransactionReceiptResponse,
    TransactionResponse,
    TransactionTimelineResponse,
)


class ReconciliationService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_transactions_paginated(
        self,
        organization_id: uuid.UUID,
        page: int = 1,
        page_size: int = 20,
        type: Optional[TransactionType] = None,
        status: Optional[TransactionStatus] = None,
        start_date: Optional[datetime.datetime] = None,
        end_date: Optional[datetime.datetime] = None,
        purchase_request_id: Optional[uuid.UUID] = None,
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ) -> PaginatedResponse[TransactionResponse]:
        """
        List transactions for this organization with robust filtering, sorting, and pagination.
        """
        stmt = select(Transaction).where(Transaction.organization_id == organization_id)
        count_stmt = select(func.count(Transaction.id)).where(Transaction.organization_id == organization_id)

        if type:
            stmt = stmt.where(Transaction.type == type)
            count_stmt = count_stmt.where(Transaction.type == type)
        if status:
            stmt = stmt.where(Transaction.status == status)
            count_stmt = count_stmt.where(Transaction.status == status)
        if purchase_request_id:
            stmt = stmt.where(Transaction.purchase_request_id == purchase_request_id)
            count_stmt = count_stmt.where(Transaction.purchase_request_id == purchase_request_id)
        if start_date:
            stmt = stmt.where(Transaction.created_at >= start_date)
            count_stmt = count_stmt.where(Transaction.created_at >= start_date)
        if end_date:
            stmt = stmt.where(Transaction.created_at <= end_date)
            count_stmt = count_stmt.where(Transaction.created_at <= end_date)

        total = (await self.session.scalar(count_stmt)) or 0

        # Dynamic sorting
        sort_column = getattr(Transaction, sort_by, Transaction.created_at)
        if sort_order.lower() == "asc":
            stmt = stmt.order_by(sort_column.asc())
        else:
            stmt = stmt.order_by(sort_column.desc())

        offset = (page - 1) * page_size
        stmt = stmt.offset(offset).limit(page_size)

        txs = list((await self.session.scalars(stmt)).all())
        items = [TransactionResponse.model_validate(t) for t in txs]
        total_pages = math.ceil(total / page_size) if page_size > 0 else 1

        return PaginatedResponse[TransactionResponse](
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def list_transactions(
        self, organization_id: uuid.UUID, skip: int = 0, limit: int = 50
    ) -> List[TransactionResponse]:
        stmt = (
            select(Transaction)
            .where(Transaction.organization_id == organization_id)
            .order_by(Transaction.created_at.desc())
            .offset(skip)
            .limit(limit)
        )
        txs = list((await self.session.scalars(stmt)).all())
        return [TransactionResponse.model_validate(t) for t in txs]

    async def get_transaction_detail(
        self, transaction_id: uuid.UUID, organization_id: uuid.UUID
    ) -> TransactionDetailResponse:
        """
        Fetch full transaction details including associated purchase request, agent, and payment attempt.
        """
        stmt = (
            select(Transaction)
            .options(
                selectinload(Transaction.purchase_request).selectinload(PurchaseRequest.agent),
                selectinload(Transaction.purchase_request).selectinload(PurchaseRequest.selected_quote),
            )
            .where(
                Transaction.id == transaction_id,
                Transaction.organization_id == organization_id,
            )
        )
        tx = await self.session.scalar(stmt)
        if not tx:
            raise NotFoundError("Transaction", transaction_id)

        pr = tx.purchase_request
        pr_summary = None
        if pr:
            sq = pr.selected_quote
            pr_summary = PurchaseSummaryForTransaction(
                id=pr.id,
                item_description=pr.item_description,
                category=pr.category,
                status=pr.status.value,
                fulfillment_status=pr.fulfillment_status.value,
                agent_id=pr.agent_id,
                agent_name=pr.agent.name if pr.agent else "Unknown Agent",
                supplier_name=sq.supplier_name if sq else None,
                unit_price=sq.unit_price if sq else None,
                quantity=sq.quantity if sq else None,
            )

        # Find latest payment attempt for this purchase
        stmt_att = (
            select(PaymentAttempt)
            .where(PaymentAttempt.purchase_request_id == tx.purchase_request_id)
            .order_by(PaymentAttempt.created_at.desc())
            .limit(1)
        )
        attempt = await self.session.scalar(stmt_att)
        att_summary = None
        if attempt:
            att_summary = PaymentAttemptSummaryForTransaction(
                id=attempt.id,
                provider=attempt.provider,
                status=attempt.status.value,
                provider_order_id=attempt.provider_order_id,
                provider_capture_id=attempt.provider_capture_id,
                approval_url=attempt.approval_url,
            )

        return TransactionDetailResponse(
            id=tx.id,
            organization_id=tx.organization_id,
            purchase_request_id=tx.purchase_request_id,
            budget_id=tx.budget_id,
            type=tx.type,
            status=tx.status,
            amount=tx.amount,
            currency=tx.currency,
            provider_transaction_id=tx.provider_transaction_id,
            created_at=tx.created_at,
            updated_at=tx.updated_at,
            purchase_request=pr_summary,
            payment_attempt=att_summary,
        )

    async def get_transaction_timeline(
        self, transaction_id: uuid.UUID, organization_id: uuid.UUID
    ) -> TransactionTimelineResponse:
        """
        Build an audit-backed chronological timeline for a transaction and its parent purchase request.
        """
        stmt_tx = select(Transaction).where(
            Transaction.id == transaction_id,
            Transaction.organization_id == organization_id,
        )
        tx = await self.session.scalar(stmt_tx)
        if not tx:
            raise NotFoundError("Transaction", transaction_id)

        # Collect all audit events referencing the purchase request or transaction
        pid_str = str(tx.purchase_request_id)
        tid_str = str(tx.id)
        cap_id = tx.provider_transaction_id or ""

        stmt_events = (
            select(AuditEvent)
            .where(
                or_(
                    AuditEvent.entity_id.in_([pid_str, tid_str, cap_id]),
                    AuditEvent.organization_id == organization_id,
                )
            )
            .order_by(AuditEvent.created_at.asc())
        )
        all_events = list((await self.session.scalars(stmt_events)).all())

        # Filter events relevant to this purchase or transaction
        relevant_events = []
        action_descriptions = {
            "PURCHASE_REQUESTED": "Purchase request submitted by agent",
            "QUOTES_COLLECTED": "Supplier quotes collected and evaluated",
            "RECOMMENDATION_GENERATED": "ML recommendation generated",
            "POLICY_EVALUATED": "Deterministic policy evaluated",
            "APPROVAL_REQUESTED": "Human approval requested",
            "APPROVAL_DECIDED": "Human approval decided",
            "PAYMENT_ORDER_CREATED": "PayPal Orders v2 order created",
            "PAYMENT_CAPTURED": "PayPal payment successfully captured",
            "PAYMENT_FAILED": "Payment capture failed or declined",
            "WEBHOOK_RECEIVED": "PayPal asynchronous webhook notification received",
            "WEBHOOK_PROCESSED": "PayPal webhook event processed",
            "PAYMENT_REFUNDED": "Payment refunded and budget recredited",
            "RECONCILIATION_PERFORMED": "Authoritative reconciliation completed",
        }

        for ev in all_events:
            is_match = False
            if ev.entity_id in (pid_str, tid_str, cap_id):
                is_match = True
            elif ev.metadata_json:
                meta_str = str(ev.metadata_json)
                if pid_str in meta_str or tid_str in meta_str or (cap_id and cap_id in meta_str):
                    is_match = True

            if is_match:
                desc = action_descriptions.get(ev.action, f"Event {ev.action} occurred")
                relevant_events.append(
                    TimelineEventItem(
                        id=ev.id,
                        timestamp=ev.created_at,
                        action=ev.action,
                        actor_type=ev.actor_type,
                        actor_id=ev.actor_id,
                        description=desc,
                        metadata_json=ev.metadata_json or {},
                    )
                )

        return TransactionTimelineResponse(
            transaction_id=tx.id,
            purchase_request_id=tx.purchase_request_id,
            events=relevant_events,
        )

    async def get_transaction_receipt(
        self, transaction_id: uuid.UUID, organization_id: uuid.UUID
    ) -> TransactionReceiptResponse:
        """
        Generate a verifiable digital receipt for accounting and compliance.
        """
        stmt = (
            select(Transaction)
            .options(
                selectinload(Transaction.organization),
                selectinload(Transaction.purchase_request).selectinload(PurchaseRequest.agent),
                selectinload(Transaction.purchase_request).selectinload(PurchaseRequest.selected_quote),
            )
            .where(
                Transaction.id == transaction_id,
                Transaction.organization_id == organization_id,
            )
        )
        tx = await self.session.scalar(stmt)
        if not tx:
            raise NotFoundError("Transaction", transaction_id)

        pr = tx.purchase_request
        org = tx.organization
        agent = pr.agent if pr else None
        quote = pr.selected_quote if pr else None

        # Fetch payment attempt for provider order reference
        stmt_att = (
            select(PaymentAttempt)
            .where(PaymentAttempt.purchase_request_id == tx.purchase_request_id)
            .order_by(PaymentAttempt.created_at.desc())
            .limit(1)
        )
        attempt = await self.session.scalar(stmt_att)

        receipt_number = f"REC-AEON-{tx.id.hex[:8].upper()}"

        return TransactionReceiptResponse(
            receipt_number=receipt_number,
            issued_at=tx.created_at,
            transaction_id=tx.id,
            organization_id=organization_id,
            organization_name=org.name if org else "AEON Organization",
            purchase_request_id=tx.purchase_request_id,
            agent_id=agent.id if agent else uuid.UUID("00000000-0000-0000-0000-000000000000"),
            agent_name=agent.name if agent else "Autonomous Agent",
            item_description=pr.item_description if pr else "Procured Goods/Services",
            category=pr.category if pr else "general",
            supplier_name=quote.supplier_name if quote else "Supplier",
            quantity=quote.quantity if quote else 1,
            unit_price=quote.unit_price if quote else tx.amount,
            total_amount=tx.amount,
            currency=tx.currency,
            status=tx.status,
            payment_method="PayPal Orders v2 (CAPTURE)",
            provider_capture_id=tx.provider_transaction_id,
            provider_order_id=attempt.provider_order_id if attempt else None,
            policy_name="Standard Spend Policy",
        )

    async def get_reconciliation_summary(self, organization_id: uuid.UUID) -> ReconciliationResponse:
        # Total spent from settled purchases
        stmt_spent = select(func.coalesce(func.sum(Transaction.amount), decimal.Decimal("0.00"))).where(
            Transaction.organization_id == organization_id,
            Transaction.type == TransactionType.PURCHASE,
            Transaction.status == TransactionStatus.SETTLED,
        )
        spent = await self.session.scalar(stmt_spent) or decimal.Decimal("0.00")

        # Total refunds
        stmt_refund = select(func.coalesce(func.sum(Transaction.amount), decimal.Decimal("0.00"))).where(
            Transaction.organization_id == organization_id,
            Transaction.type == TransactionType.REFUND,
        )
        refunded = await self.session.scalar(stmt_refund) or decimal.Decimal("0.00")

        # Counts
        stmt_all = select(Transaction).where(Transaction.organization_id == organization_id)
        all_tx = list((await self.session.scalars(stmt_all)).all())

        pending_c = sum(1 for t in all_tx if t.status == TransactionStatus.PENDING)
        settled_c = sum(1 for t in all_tx if t.status == TransactionStatus.SETTLED)
        failed_c = sum(1 for t in all_tx if t.status == TransactionStatus.FAILED)

        return ReconciliationResponse(
            total_transactions_count=len(all_tx),
            total_spent_amount=spent,
            total_refunded_amount=refunded,
            currency="USD",
            pending_count=pending_c,
            settled_count=settled_c,
            failed_count=failed_c,
            reconciled_at=datetime.datetime.now(datetime.timezone.utc),
        )
