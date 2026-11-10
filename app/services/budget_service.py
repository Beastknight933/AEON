import datetime
import decimal
import uuid
from typing import List, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.errors import NotFoundError
from app.models.budget import Budget, BudgetReservation
from app.repositories.budget_repo import BudgetRepository
from app.schemas.budget import (
    BudgetCreateRequest,
    BudgetResponse,
    BudgetUpdateRequest,
    BudgetReservationResponse,
)


class BudgetService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.budget_repo = BudgetRepository(session)

    async def create_budget(self, organization_id: uuid.UUID, req: BudgetCreateRequest) -> BudgetResponse:
        start_date = req.start_date or datetime.datetime.now(datetime.timezone.utc)
        budget = Budget(
            organization_id=organization_id,
            agent_id=req.agent_id,
            name=req.name.strip(),
            currency=req.currency.upper(),
            allocated_amount=req.allocated_amount,
            reserved_amount=decimal.Decimal("0.00"),
            spent_amount=decimal.Decimal("0.00"),
            start_date=start_date,
            end_date=req.end_date,
            is_active=True,
        )
        created = await self.budget_repo.create(budget)
        await self.session.commit()
        await self.session.refresh(created)
        return BudgetResponse.model_validate(created)

    async def list_budgets(self, organization_id: uuid.UUID) -> List[BudgetResponse]:
        budgets = await self.budget_repo.list_by_org(organization_id)
        return [BudgetResponse.model_validate(b) for b in budgets]

    async def get_budget(self, budget_id: uuid.UUID, organization_id: uuid.UUID) -> BudgetResponse:
        budget = await self.budget_repo.get_by_id(budget_id, org_id=organization_id)
        if not budget:
            raise NotFoundError("Budget", budget_id)
        return BudgetResponse.model_validate(budget)

    async def update_budget(
        self, budget_id: uuid.UUID, organization_id: uuid.UUID, req: BudgetUpdateRequest
    ) -> BudgetResponse:
        budget = await self.budget_repo.get_by_id(budget_id, org_id=organization_id)
        if not budget:
            raise NotFoundError("Budget", budget_id)

        if req.name is not None:
            budget.name = req.name.strip()
        if req.allocated_amount is not None:
            budget.allocated_amount = req.allocated_amount
        if req.is_active is not None:
            budget.is_active = req.is_active
        if req.end_date is not None:
            budget.end_date = req.end_date

        await self.budget_repo.update(budget)
        await self.session.commit()
        await self.session.refresh(budget)
        return BudgetResponse.model_validate(budget)

    async def reserve_budget(
        self,
        budget_id: uuid.UUID,
        purchase_request_id: uuid.UUID,
        amount: decimal.Decimal,
        currency: str = "USD",
    ) -> BudgetReservationResponse:
        reservation = await self.budget_repo.reserve_funds_atomic(
            budget_id=budget_id,
            purchase_request_id=purchase_request_id,
            amount=amount,
            currency=currency,
        )
        await self.session.commit()
        await self.session.refresh(reservation)
        return BudgetReservationResponse.model_validate(reservation)

    async def settle_reservation(self, reservation_id: uuid.UUID) -> BudgetReservationResponse:
        reservation = await self.budget_repo.settle_reservation_atomic(reservation_id)
        await self.session.commit()
        await self.session.refresh(reservation)
        return BudgetReservationResponse.model_validate(reservation)

    async def release_reservation(self, reservation_id: uuid.UUID) -> BudgetReservationResponse:
        reservation = await self.budget_repo.release_reservation_atomic(reservation_id)
        await self.session.commit()
        await self.session.refresh(reservation)
        return BudgetReservationResponse.model_validate(reservation)

    async def list_reservations(
        self, budget_id: uuid.UUID, organization_id: uuid.UUID
    ) -> List[BudgetReservationResponse]:
        budget = await self.budget_repo.get_by_id(budget_id, org_id=organization_id)
        if not budget:
            raise NotFoundError("Budget", budget_id)
        reservations = await self.budget_repo.list_reservations_by_budget(budget_id)
        return [BudgetReservationResponse.model_validate(r) for r in reservations]
