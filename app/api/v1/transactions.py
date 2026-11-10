import datetime
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_and_membership
from app.core.constants import TransactionStatus, TransactionType
from app.core.database import get_db
from app.models.organization import Membership, Organization, User
from app.schemas.common import PaginatedResponse
from app.schemas.transaction import (
    ReconciliationResponse,
    TransactionDetailResponse,
    TransactionReceiptResponse,
    TransactionResponse,
    TransactionTimelineResponse,
)
from app.services.reconciliation_service import ReconciliationService

router = APIRouter(prefix="/transactions", tags=["Transactions & Financial Ledger"])


@router.get("", response_model=PaginatedResponse[TransactionResponse])
async def list_transactions(
    page: int = Query(1, ge=1, description="Page number (1-based)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    type: Optional[TransactionType] = Query(None, description="Filter by transaction type (PURCHASE, REFUND)"),
    status: Optional[TransactionStatus] = Query(None, description="Filter by status (SETTLED, PENDING, FAILED, REFUNDED)"),
    purchase_request_id: Optional[uuid.UUID] = Query(None, description="Filter by purchase request ID"),
    start_date: Optional[datetime.datetime] = Query(None, description="Filter transactions on or after UTC datetime"),
    end_date: Optional[datetime.datetime] = Query(None, description="Filter transactions on or before UTC datetime"),
    sort_by: str = Query("created_at", description="Field to sort by"),
    sort_order: str = Query("desc", pattern="^(asc|desc)$", description="Sort order: asc or desc"),
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    List transactions from the immutable financial ledger with filtering, pagination, and sorting.
    """
    _, _, org = context
    service = ReconciliationService(db)
    return await service.list_transactions_paginated(
        organization_id=org.id,
        page=page,
        page_size=page_size,
        type=type,
        status=status,
        purchase_request_id=purchase_request_id,
        start_date=start_date,
        end_date=end_date,
        sort_by=sort_by,
        sort_order=sort_order,
    )


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


@router.get("/{transaction_id}", response_model=TransactionDetailResponse)
async def get_transaction_detail(
    transaction_id: uuid.UUID,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Get detailed transaction record including associated purchase request, agent, and payment attempt.
    """
    _, _, org = context
    service = ReconciliationService(db)
    return await service.get_transaction_detail(transaction_id, org.id)


@router.get("/{transaction_id}/timeline", response_model=TransactionTimelineResponse)
async def get_transaction_timeline(
    transaction_id: uuid.UUID,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Get audit-backed chronological lifecycle events from purchase inception to payment capture and fulfillment.
    """
    _, _, org = context
    service = ReconciliationService(db)
    return await service.get_transaction_timeline(transaction_id, org.id)


@router.get("/{transaction_id}/receipt", response_model=TransactionReceiptResponse)
async def get_transaction_receipt(
    transaction_id: uuid.UUID,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Generate an audit-grade digital receipt for accounting and compliance.
    """
    _, _, org = context
    service = ReconciliationService(db)
    return await service.get_transaction_receipt(transaction_id, org.id)
