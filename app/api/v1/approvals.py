import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import require_roles
from app.core.constants import ApprovalStatus, UserRole
from app.core.database import get_db
from app.models.organization import Membership, Organization, User
from app.schemas.approval import ApprovalDecideRequest, ApprovalDetailResponse, ApprovalResponse
from app.services.approval_service import ApprovalService

router = APIRouter(prefix="/approvals", tags=["Human Approvals"])


@router.get("", response_model=List[ApprovalResponse])
async def list_approvals(
    status: Optional[ApprovalStatus] = Query(None, description="Filter approvals by status"),
    context: tuple[User, Membership, Organization] = Depends(
        require_roles([UserRole.ADMIN, UserRole.APPROVER])
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    List purchase approvals awaiting or decided by human approvers in the organization.
    Restricted to ADMIN and APPROVER roles.
    """
    _, _, org = context
    service = ApprovalService(db)
    return await service.list_approvals(org.id, status=status)


@router.get("/{approval_id}", response_model=ApprovalDetailResponse)
async def get_approval(
    approval_id: uuid.UUID,
    context: tuple[User, Membership, Organization] = Depends(
        require_roles([UserRole.ADMIN, UserRole.APPROVER])
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve comprehensive details for a specific approval, including bound quote and purchase information.
    """
    _, _, org = context
    service = ApprovalService(db)
    return await service.get_approval(approval_id, org.id)


@router.post("/{approval_id}/decide", response_model=ApprovalResponse)
async def decide_approval(
    approval_id: uuid.UUID,
    req: ApprovalDecideRequest,
    context: tuple[User, Membership, Organization] = Depends(
        require_roles([UserRole.ADMIN, UserRole.APPROVER])
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    Approve or reject a pending purchase request.
    Verifies that the underlying purchase, selected quote, and policy have not changed or expired.
    Note: Hard policy violations can never be overridden by human approval.
    """
    user, _, org = context
    service = ApprovalService(db)
    return await service.decide_approval(
        approval_id=approval_id,
        approver_id=user.id,
        organization_id=org.id,
        req=req,
    )
