import uuid
from typing import List
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_and_membership, require_roles
from app.core.constants import UserRole
from app.core.database import get_db
from app.models.organization import Membership, Organization, User
from app.schemas.policy import (
    PolicyAssignmentRequest,
    PolicyAssignmentResponse,
    PolicyCreateRequest,
    PolicyResponse,
    PolicyVersionCreate,
    PolicyVersionResponse,
)
from app.services.policy_service import PolicyService

router = APIRouter(prefix="/policies", tags=["Procurement Policies"])


@router.post("", response_model=PolicyResponse, status_code=status.HTTP_201_CREATED)
async def create_policy(
    req: PolicyCreateRequest,
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Create a new procurement policy with initial deterministic constraints (version 1).
    """
    _, _, org = context
    service = PolicyService(db)
    return await service.create_policy(org.id, req)


@router.get("", response_model=List[PolicyResponse])
async def list_policies(
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    List all policies for the authenticated organization.
    """
    _, _, org = context
    service = PolicyService(db)
    return await service.list_policies(org.id)


@router.get("/{policy_id}", response_model=PolicyResponse)
async def get_policy(
    policy_id: uuid.UUID,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve full details and versions of a specific procurement policy.
    """
    _, _, org = context
    service = PolicyService(db)
    return await service.get_policy(policy_id, org.id)


@router.post("/{policy_id}/versions", response_model=PolicyVersionResponse, status_code=status.HTTP_201_CREATED)
async def add_policy_version(
    policy_id: uuid.UUID,
    req: PolicyVersionCreate,
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Append an immutable new version to an existing policy.
    """
    _, _, org = context
    service = PolicyService(db)
    return await service.add_version(policy_id, org.id, req)


@router.post("/assignments/{agent_id}", response_model=PolicyAssignmentResponse)
async def assign_policy_to_agent(
    agent_id: uuid.UUID,
    req: PolicyAssignmentRequest,
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Assign a procurement policy to an autonomous agent.
    """
    _, _, org = context
    service = PolicyService(db)
    return await service.assign_to_agent(agent_id, req.policy_id, org.id)
