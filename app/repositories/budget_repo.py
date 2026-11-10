import decimal
import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.constants import ReservationStatus
from app.core.errors import BudgetExceededError, NotFoundError, StateTransitionError
from app.models.budget import Budget, BudgetReservation


class BudgetRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, budget_id: uuid.UUID, org_id: Optional[uuid.UUID] = None) -> Optional[Budget]:
        stmt = select(Budget).where(Budget.id == budget_id)
        if org_id:
            stmt = stmt.where(Budget.organization_id == org_id)
        return await self.session.scalar(stmt)

    async def list_by_org(self, org_id: uuid.UUID) -> List[Budget]:
        stmt = select(Budget).where(Budget.organization_id == org_id).order_by(Budget.created_at.desc())
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def create(self, budget: Budget) -> Budget:
        self.session.add(budget)
        await self.session.flush()
        return budget

    async def update(self, budget: Budget) -> Budget:
        self.session.add(budget)
        await self.session.flush()
        return budget

    async def get_budget_for_agent_or_org(
        self, organization_id: uuid.UUID, agent_id: Optional[uuid.UUID] = None
    ) -> Optional[Budget]:
        """
        Look for an active budget specifically assigned to the agent first.
        If none exists, look for an active organization-wide budget (agent_id is None).
        """
        if agent_id:
            stmt = select(Budget).where(
                Budget.organization_id == organization_id,
                Budget.agent_id == agent_id,
                Budget.is_active.is_(True),
            ).order_by(Budget.created_at.desc()).limit(1)
            agent_budget = await self.session.scalar(stmt)
            if agent_budget:
                return agent_budget

        # Fallback to org-wide general budget
        stmt = select(Budget).where(
            Budget.organization_id == organization_id,
            Budget.agent_id.is_(None),
            Budget.is_active.is_(True),
        ).order_by(Budget.created_at.desc()).limit(1)
        return await self.session.scalar(stmt)

    async def reserve_funds_atomic(
        self,
        budget_id: uuid.UUID,
        purchase_request_id: uuid.UUID,
        amount: decimal.Decimal,
        currency: str = "USD",
    ) -> BudgetReservation:
        """
        Atomic budget reservation using row-level locking.
        Ensures available_amount >= amount before mutating reservation.
        """
        # Row-level lock on the budget row
        stmt = select(Budget).where(Budget.id == budget_id).with_for_update()
        budget = await self.session.scalar(stmt)
        if not budget or not budget.is_active:
            raise NotFoundError("Active Budget", budget_id)

        available = budget.allocated_amount - budget.reserved_amount - budget.spent_amount
        if available < amount:
            raise BudgetExceededError(
                f"Insufficient available budget: requested {amount} {currency}, available {available} {budget.currency}",
                details={
                    "budget_id": str(budget.id),
                    "requested_amount": str(amount),
                    "available_amount": str(available),
                    "allocated_amount": str(budget.allocated_amount),
                    "reserved_amount": str(budget.reserved_amount),
                    "spent_amount": str(budget.spent_amount),
                },
            )

        budget.reserved_amount += amount
        reservation = BudgetReservation(
            budget_id=budget.id,
            purchase_request_id=purchase_request_id,
            amount=amount,
            currency=currency,
            status=ReservationStatus.ACTIVE,
        )
        self.session.add(reservation)
        await self.session.flush()
        return reservation

    async def get_reservation_by_id(self, reservation_id: uuid.UUID) -> Optional[BudgetReservation]:
        stmt = select(BudgetReservation).where(BudgetReservation.id == reservation_id)
        return await self.session.scalar(stmt)

    async def get_reservation_by_purchase(self, purchase_request_id: uuid.UUID) -> Optional[BudgetReservation]:
        stmt = select(BudgetReservation).where(
            BudgetReservation.purchase_request_id == purchase_request_id
        ).order_by(BudgetReservation.created_at.desc()).limit(1)
        return await self.session.scalar(stmt)

    async def settle_reservation_atomic(self, reservation_id: uuid.UUID) -> BudgetReservation:
        """
        Settles an active reservation into spent funds.
        """
        res_stmt = select(BudgetReservation).where(BudgetReservation.id == reservation_id).with_for_update()
        reservation = await self.session.scalar(res_stmt)
        if not reservation:
            raise NotFoundError("BudgetReservation", reservation_id)

        if reservation.status != ReservationStatus.ACTIVE:
            raise StateTransitionError(
                current_state=reservation.status.value,
                attempted_state=ReservationStatus.SETTLED.value,
                entity="BudgetReservation",
            )

        b_stmt = select(Budget).where(Budget.id == reservation.budget_id).with_for_update()
        budget = await self.session.scalar(b_stmt)
        if not budget:
            raise NotFoundError("Budget", reservation.budget_id)

        # Settle: reduce reserved, increase spent
        budget.reserved_amount -= reservation.amount
        budget.spent_amount += reservation.amount
        reservation.status = ReservationStatus.SETTLED
        await self.session.flush()
        return reservation

    async def release_reservation_atomic(self, reservation_id: uuid.UUID) -> BudgetReservation:
        """
        Releases an active reservation back to available funds.
        """
        res_stmt = select(BudgetReservation).where(BudgetReservation.id == reservation_id).with_for_update()
        reservation = await self.session.scalar(res_stmt)
        if not reservation:
            raise NotFoundError("BudgetReservation", reservation_id)

        if reservation.status != ReservationStatus.ACTIVE:
            raise StateTransitionError(
                current_state=reservation.status.value,
                attempted_state=ReservationStatus.RELEASED.value,
                entity="BudgetReservation",
            )

        b_stmt = select(Budget).where(Budget.id == reservation.budget_id).with_for_update()
        budget = await self.session.scalar(b_stmt)
        if not budget:
            raise NotFoundError("Budget", reservation.budget_id)

        budget.reserved_amount -= reservation.amount
        reservation.status = ReservationStatus.RELEASED
        await self.session.flush()
        return reservation

    async def record_refund_atomic(self, budget_id: uuid.UUID, amount: decimal.Decimal) -> Budget:
        """
        Refunds spent funds back to the budget.
        """
        b_stmt = select(Budget).where(Budget.id == budget_id).with_for_update()
        budget = await self.session.scalar(b_stmt)
        if not budget:
            raise NotFoundError("Budget", budget_id)

        budget.spent_amount = max(decimal.Decimal("0.00"), budget.spent_amount - amount)
        await self.session.flush()
        return budget
