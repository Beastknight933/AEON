import uuid
from typing import Optional, List
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.organization import Organization, Membership


class OrganizationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, org_id: uuid.UUID) -> Optional[Organization]:
        stmt = select(Organization).where(Organization.id == org_id)
        return await self.session.scalar(stmt)

    async def get_by_slug(self, slug: str) -> Optional[Organization]:
        stmt = select(Organization).where(Organization.slug == slug)
        return await self.session.scalar(stmt)

    async def get_by_name(self, name: str) -> Optional[Organization]:
        stmt = select(Organization).where(Organization.name == name)
        return await self.session.scalar(stmt)

    async def create(self, organization: Organization) -> Organization:
        self.session.add(organization)
        await self.session.flush()
        return organization

    async def add_membership(self, membership: Membership) -> Membership:
        self.session.add(membership)
        await self.session.flush()
        return membership

    async def get_membership(self, user_id: uuid.UUID, org_id: uuid.UUID) -> Optional[Membership]:
        stmt = select(Membership).where(
            Membership.user_id == user_id,
            Membership.organization_id == org_id,
        )
        return await self.session.scalar(stmt)

    async def get_user_memberships(self, user_id: uuid.UUID) -> List[Membership]:
        stmt = select(Membership).where(Membership.user_id == user_id)
        result = await self.session.scalars(stmt)
        return list(result.all())
