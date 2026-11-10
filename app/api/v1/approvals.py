import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_and_membership, require_roles
from app.core.constants import UserRole
from app.core.database import get_db
from app.models.organization import Membership, Organization, User
from app.schemas.approval import ApprovalDecideRequest, ApprovalResponse
from app.services.approval_service import ApprovalService

router = APIRouter(prefix="/approvals", tags=["Human Approvals"])


@router.get("", response_model=List[ApprovalResponse])
async def list_pending_approvals(
    context: tuple[User, Membership, Organization] = Depends(
        require_roles([UserRole.ADMIN, UserRole.APPROVER])
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    List all pending purchase approvals awaiting human review in the organization.
    """
    _, _, org = context
    service = ApprovalService(db)
    return await service.list_pending_approvals(org.id)


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
