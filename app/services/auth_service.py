import re
import uuid
from typing import Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.constants import UserRole
from app.core.errors import ConflictError, InvalidCredentialsError, NotFoundError, AuthenticationError
from app.core.security import hash_password, verify_password, create_access_token
from app.models.organization import Organization, User, Membership
from app.repositories.organization_repo import OrganizationRepository
from app.repositories.user_repo import UserRepository
from app.schemas.auth import UserRegisterRequest, UserLoginRequest, TokenResponse


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")


class AuthService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.user_repo = UserRepository(session)
        self.org_repo = OrganizationRepository(session)

    async def register(self, req: UserRegisterRequest) -> Tuple[User, Organization, Membership, TokenResponse]:
        # Check email uniqueness
        existing_user = await self.user_repo.get_by_email(req.email)
        if existing_user:
            raise ConflictError(f"User with email '{req.email}' already exists")

        # Create or find organization
        base_slug = slugify(req.organization_name)
        slug = base_slug
        counter = 1
        while await self.org_repo.get_by_slug(slug):
            slug = f"{base_slug}-{counter}"
            counter += 1

        org = Organization(name=req.organization_name.strip(), slug=slug)
        await self.org_repo.create(org)

        # Create user
        user = User(
            email=req.email.lower().strip(),
            hashed_password=hash_password(req.password),
            full_name=req.full_name.strip(),
            is_active=True,
        )
        await self.user_repo.create(user)

        # Create membership as ADMIN
        membership = Membership(
            user_id=user.id,
            organization_id=org.id,
            role=UserRole.ADMIN,
        )
        await self.org_repo.add_membership(membership)

        await self.session.commit()
        await self.session.refresh(user)
        await self.session.refresh(org)
        await self.session.refresh(membership)

        # Create token
        token_str = create_access_token(
            subject=str(user.id),
            claims={
                "org_id": str(org.id),
                "role": membership.role.value,
                "email": user.email,
            },
        )
        token = TokenResponse(access_token=token_str, expires_in_minutes=60)
        return user, org, membership, token

    async def login(self, req: UserLoginRequest) -> Tuple[User, Organization, Membership, TokenResponse]:
        user = await self.user_repo.get_by_email(req.email)
        if not user:
            raise InvalidCredentialsError("Invalid email or password")

        if not verify_password(req.password, user.hashed_password):
            raise InvalidCredentialsError("Invalid email or password")

        if not user.is_active:
            raise AuthenticationError("User account is inactive")

        # Get memberships
        memberships = await self.org_repo.get_user_memberships(user.id)
        if not memberships:
            raise AuthenticationError("User does not belong to any active organization")

        primary_membership = memberships[0]
        org = await self.org_repo.get_by_id(primary_membership.organization_id)
        if not org:
            raise NotFoundError("Organization", primary_membership.organization_id)

        token_str = create_access_token(
            subject=str(user.id),
            claims={
                "org_id": str(org.id),
                "role": primary_membership.role.value,
                "email": user.email,
            },
        )
        token = TokenResponse(access_token=token_str, expires_in_minutes=60)
        return user, org, primary_membership, token
