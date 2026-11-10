import datetime
import decimal
import uuid
from typing import List
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import TransactionStatus, TransactionType
from app.models.transaction import Transaction
from app.schemas.transaction import ReconciliationResponse, TransactionResponse


class ReconciliationService:
    def __init__(self, session: AsyncSession):
        self.session = session

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
