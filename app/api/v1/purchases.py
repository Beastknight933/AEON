import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    get_authenticated_agent,
    get_current_user_and_membership,
)
from app.core.constants import PurchaseStatus
from app.core.database import get_db
from app.models.agent import Agent, AgentCredential
from app.models.organization import Membership, Organization, User
from app.schemas.purchase import (
    PurchaseDetailResponse,
    PurchaseListResponse,
    PurchaseSubmitRequest,
)
from app.services.procurement_service import ProcurementService

router = APIRouter(prefix="/purchases", tags=["Agent Procurement"])


@router.post("", response_model=PurchaseDetailResponse, status_code=status.HTTP_201_CREATED)
async def submit_purchase_request(
    req: PurchaseSubmitRequest,
    agent_context: tuple[Agent, AgentCredential, Organization] = Depends(get_authenticated_agent),
    db: AsyncSession = Depends(get_db),
):
    """
    Submit a purchase request as an autonomous agent.
    Runs the complete 10-step procurement pipeline:
    quote collection -> ML recommendation -> deterministic policy check -> budget reservation -> approval routing / authorization.
    """
    agent, _, org = agent_context
    service = ProcurementService(db)
    return await service.execute_procurement_pipeline(agent=agent, organization=org, req=req)


@router.get("", response_model=List[PurchaseListResponse])
async def list_purchases(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[PurchaseStatus] = Query(None),
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    List purchase requests for the current organization with pagination and optional status filter.
    """
    _, _, org = context
    service = ProcurementService(db)
    return await service.list_purchases(org.id, skip=skip, limit=limit, status=status)


@router.get("/{purchase_id}", response_model=PurchaseDetailResponse)
async def get_purchase(
    purchase_id: uuid.UUID,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve comprehensive details, supplier quotes, recommendation, and policy decision for a purchase.
    """
    _, _, org = context
    service = ProcurementService(db)
    return await service.get_purchase_detail(purchase_id, org.id)
