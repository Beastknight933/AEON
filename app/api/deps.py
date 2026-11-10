import uuid
from typing import Annotated, List, Optional, Tuple
from fastapi import Depends, Header, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import UserRole
from app.core.database import get_db
from app.core.errors import AuthenticationError, AuthorizationError, NotFoundError
from app.core.security import decode_access_token
from app.models.agent import Agent, AgentCredential
from app.models.organization import Membership, Organization, User
from app.repositories.agent_repo import AgentRepository
from app.repositories.organization_repo import OrganizationRepository
from app.repositories.user_repo import UserRepository

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user_and_membership(
    credentials: Annotated[Optional[HTTPAuthorizationCredentials], Security(bearer_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Tuple[User, Membership, Organization]:
    """
    Authenticate dashboard user via JWT Bearer token and resolve active organization context.
    """
    if not credentials or not credentials.credentials:
        raise AuthenticationError("Authorization header with Bearer token is required")

    token = credentials.credentials
    payload = decode_access_token(token)
    user_id_str = payload.get("sub")
    org_id_str = payload.get("org_id")

    if not user_id_str:
        raise AuthenticationError("Invalid token payload: missing sub")

    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise AuthenticationError("Invalid user ID format in token")

    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(user_id)
    if not user or not user.is_active:
        raise AuthenticationError("User is not found or account is deactivated")

    org_repo = OrganizationRepository(db)
    if org_id_str:
        try:
            org_id = uuid.UUID(org_id_str)
        except ValueError:
            raise AuthenticationError("Invalid organization ID format in token")
        membership = await org_repo.get_membership(user_id=user.id, org_id=org_id)
    else:
        memberships = await org_repo.get_user_memberships(user.id)
        membership = memberships[0] if memberships else None

    if not membership:
        raise AuthorizationError("User is not a member of the requested organization")

    org = await org_repo.get_by_id(membership.organization_id)
    if not org:
        raise NotFoundError("Organization", membership.organization_id)

    return user, membership, org


def require_roles(allowed_roles: List[UserRole]):
    async def role_checker(
        context: Tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    ) -> Tuple[User, Membership, Organization]:
        _, membership, _ = context
        if membership.role not in allowed_roles:
            raise AuthorizationError(
                f"Action requires one of roles: {[r.value for r in allowed_roles]}, but user has {membership.role.value}"
            )
        return context

    return role_checker


async def get_authenticated_agent(
    db: Annotated[AsyncSession, Depends(get_db)],
    x_agent_api_key: Optional[str] = Header(None, alias="X-Agent-API-Key"),
    auth_header: Optional[HTTPAuthorizationCredentials] = Security(bearer_scheme),
) -> Tuple[Agent, AgentCredential, Organization]:
    """
    Authenticate autonomous AI agents via cryptographically secure API credentials.
    Supports either X-Agent-API-Key header or Bearer aeon_live_...
    Never trusts caller-supplied agent_id or organization_id.
    """
    raw_key: Optional[str] = None
    if x_agent_api_key:
        raw_key = x_agent_api_key.strip()
    elif auth_header and auth_header.credentials.startswith("aeon_live_"):
        raw_key = auth_header.credentials.strip()

    if not raw_key:
        raise AuthenticationError("Agent API key required (via X-Agent-API-Key header or Bearer key)")

    agent_repo = AgentRepository(db)
    auth_result = await agent_repo.authenticate_by_raw_key(raw_key)
    if not auth_result:
        raise AuthenticationError("Invalid, expired, or revoked Agent API key")

    agent, credential = auth_result
    org_repo = OrganizationRepository(db)
    org = await org_repo.get_by_id(agent.organization_id)
    if not org:
        raise AuthenticationError("Organization associated with agent does not exist")

    return agent, credential, org
