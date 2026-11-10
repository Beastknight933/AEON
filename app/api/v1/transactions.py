from typing import List
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_and_membership
from app.core.database import get_db
from app.models.organization import Membership, Organization, User
from app.schemas.transaction import ReconciliationResponse, TransactionResponse
from app.services.reconciliation_service import ReconciliationService

router = APIRouter(prefix="/transactions", tags=["Transactions & Reconciliation"])


@router.get("", response_model=List[TransactionResponse])
async def list_transactions(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    List transactions recorded in the financial ledger for this organization.
    """
    _, _, org = context
    service = ReconciliationService(db)
    return await service.list_transactions(org.id, skip=skip, limit=limit)


@router.get("/reconcile", response_model=ReconciliationResponse)
async def get_reconciliation_summary(
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Get audit and financial reconciliation summary of all transactions and settled spend.
    """
    _, _, org = context
    service = ReconciliationService(db)
    return await service.get_reconciliation_summary(org.id)
