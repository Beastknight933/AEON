from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_and_membership
from app.core.database import get_db
from app.models.organization import Membership, Organization, User
from app.schemas.auth import (
    CurrentUserWithOrgResponse,
    OrganizationResponse,
    TokenResponse,
    UserLoginRequest,
    UserRegisterRequest,
    UserResponse,
)
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication & Identity"])


@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
async def register(
    req: UserRegisterRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Register a new administrator, provision an organization, and return an access token.
    """
    auth_service = AuthService(db)
    _, _, _, token = await auth_service.register(req)
    return token


@router.post("/login", response_model=TokenResponse)
async def login(
    req: UserLoginRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Authenticate administrator credentials and return an access token.
    """
    auth_service = AuthService(db)
    _, _, _, token = await auth_service.login(req)
    return token


@router.get("/me", response_model=CurrentUserWithOrgResponse)
async def get_current_user_profile(
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
):
    """
    Retrieve profile and organization context of the authenticated dashboard user.
    """
    user, membership, org = context
    return CurrentUserWithOrgResponse(
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse.model_validate(org),
        role=membership.role,
    )
