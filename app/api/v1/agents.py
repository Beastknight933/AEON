import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_and_membership, require_roles
from app.core.constants import UserRole
from app.core.database import get_db
from app.models.organization import Membership, Organization, User
from app.schemas.agent import (
    AgentCreatedWithKeyResponse,
    AgentCreateRequest,
    AgentCredentialResponse,
    AgentKeyGenerateResponse,
    AgentResponse,
    AgentUpdateRequest,
)
from app.services.agent_service import AgentService

router = APIRouter(prefix="/agents", tags=["Agents & Identity"])


@router.post("", response_model=AgentCreatedWithKeyResponse, status_code=status.HTTP_201_CREATED)
async def create_agent(
    req: AgentCreateRequest,
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new autonomous AI agent and issue its initial API credentials.
    The raw API key is returned ONLY once in this response.
    """
    _, _, org = context
    service = AgentService(db)
    return await service.create_agent_with_key(org.id, req)


@router.get("", response_model=List[AgentResponse])
async def list_agents(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=100),
    is_active: Optional[bool] = Query(None),
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    List all agents belonging to the authenticated organization.
    """
    _, _, org = context
    service = AgentService(db)
    return await service.list_agents(org.id, skip=skip, limit=limit, is_active=is_active)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: uuid.UUID,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Retrieve details of a specific agent.
    """
    _, _, org = context
    service = AgentService(db)
    return await service.get_agent(agent_id, org.id)


@router.patch("/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: uuid.UUID,
    req: AgentUpdateRequest,
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Update agent metadata or active status.
    """
    _, _, org = context
    service = AgentService(db)
    return await service.update_agent(agent_id, org.id, req)


@router.post("/{agent_id}/keys/rotate", response_model=AgentKeyGenerateResponse)
async def rotate_agent_key(
    agent_id: uuid.UUID,
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Rotate an agent's API credentials. Revokes all active credentials and issues a new one.
    """
    _, _, org = context
    service = AgentService(db)
    return await service.rotate_agent_key(agent_id, org.id)


@router.get("/{agent_id}/keys", response_model=List[AgentCredentialResponse])
async def list_agent_credentials(
    agent_id: uuid.UUID,
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    List all credential records (prefix and status) for an agent.
    Raw keys and hashes are never exposed.
    """
    _, _, org = context
    service = AgentService(db)
    return await service.list_agent_credentials(agent_id, org.id)


@router.delete("/{agent_id}/keys/{credential_id}", response_model=AgentCredentialResponse)
async def revoke_agent_credential(
    agent_id: uuid.UUID,
    credential_id: uuid.UUID,
    context: tuple[User, Membership, Organization] = Depends(require_roles([UserRole.ADMIN])),
    db: AsyncSession = Depends(get_db),
):
    """
    Immediately revoke a specific agent credential.
    """
    _, _, org = context
    service = AgentService(db)
    return await service.revoke_credential(credential_id, org.id)
