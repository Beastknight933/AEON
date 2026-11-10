import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_and_membership, require_roles
from app.core.constants import UserRole
from app.core.database import get_db
from app.models.organization import Membership, Organization, User
from app.schemas.budget import (
    BudgetCreateRequest,
    BudgetReservationCreateRequest,
    BudgetReservationResponse,
    BudgetResponse,
    BudgetUpdateRequest,
)
from app.services.budget_service import BudgetService

router = APIRouter(prefix="/budgets", tags=["Budgets & Integrity"])


@router.post("", response_model=BudgetResponse, status_code=status.HTTP_201_CREATED)
async def create_budget(
    req: BudgetCreateRequest,
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Allocate a new budget for the organization or a designated agent.
    """
    _, _, org = context
    service = BudgetService(db)
    return await service.create_budget(org.id, req)


@router.get("", response_model=List[BudgetResponse])
async def list_budgets(
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    List all active and historical budgets for the organization.
    """
    _, _, org = context
    service = BudgetService(db)
    return await service.list_budgets(org.id)


@router.get("/{budget_id}", response_model=BudgetResponse)
async def get_budget(
    budget_id: uuid.UUID,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Get current allocation, reserved, spent, and available amounts for a budget.
    """
    _, _, org = context
    service = BudgetService(db)
    return await service.get_budget(budget_id, org.id)


@router.patch("/{budget_id}", response_model=BudgetResponse)
async def update_budget(
    budget_id: uuid.UUID,
    req: BudgetUpdateRequest,
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Update budget allocation or lifecycle status.
    """
    _, _, org = context
    service = BudgetService(db)
    return await service.update_budget(budget_id, org.id, req)


@router.post("/{budget_id}/reserve", response_model=BudgetReservationResponse, status_code=status.HTTP_201_CREATED)
async def reserve_budget(
    budget_id: uuid.UUID,
    req: BudgetReservationCreateRequest,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Perform an atomic budget reservation with row-level locking.
    Prevents concurrent race conditions and overspending across agents.
    """
    _, _, org = context
    service = BudgetService(db)
    # Validate budget belongs to organization
    await service.get_budget(budget_id, org.id)
    return await service.reserve_budget(
        budget_id=budget_id,
        purchase_request_id=req.purchase_request_id,
        amount=req.amount,
        currency=req.currency,
    )


@router.post("/reservations/{reservation_id}/settle", response_model=BudgetReservationResponse)
async def settle_reservation(
    reservation_id: uuid.UUID,
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Settle an active budget reservation into spent funds upon successful transaction.
    """
    service = BudgetService(db)
    return await service.settle_reservation(reservation_id)


@router.post("/reservations/{reservation_id}/release", response_model=BudgetReservationResponse)
async def release_reservation(
    reservation_id: uuid.UUID,
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Release an active budget reservation back into available funds upon cancellation or failure.
    """
    service = BudgetService(db)
    return await service.release_reservation(reservation_id)


@router.get("/{budget_id}/reservations", response_model=List[BudgetReservationResponse])
async def list_budget_reservations(
    budget_id: uuid.UUID,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    List all reservations for a specific budget.
    """
    _, _, org = context
    service = BudgetService(db)
    return await service.list_reservations(budget_id, org.id)
