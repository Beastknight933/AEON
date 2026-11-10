import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.policy import Policy, PolicyVersion, AgentPolicyAssignment


class PolicyRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, policy_id: uuid.UUID, org_id: Optional[uuid.UUID] = None) -> Optional[Policy]:
        stmt = (
            select(Policy)
            .options(selectinload(Policy.versions))
            .where(Policy.id == policy_id)
        )
        if org_id:
            stmt = stmt.where(Policy.organization_id == org_id)
        return await self.session.scalar(stmt)

    async def list_by_org(self, org_id: uuid.UUID) -> List[Policy]:
        stmt = (
            select(Policy)
            .options(selectinload(Policy.versions))
            .where(Policy.organization_id == org_id)
            .order_by(Policy.created_at.desc())
        )
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def create(self, policy: Policy, initial_version: PolicyVersion) -> Policy:
        self.session.add(policy)
        await self.session.flush()
        initial_version.policy_id = policy.id
        self.session.add(initial_version)
        await self.session.flush()
        return policy

    async def add_version(self, version: PolicyVersion) -> PolicyVersion:
        self.session.add(version)
        await self.session.flush()
        return version

    async def get_latest_version(self, policy_id: uuid.UUID) -> Optional[PolicyVersion]:
        stmt = (
            select(PolicyVersion)
            .where(PolicyVersion.policy_id == policy_id)
            .order_by(PolicyVersion.version.desc())
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def get_active_assignment_for_agent(self, agent_id: uuid.UUID) -> Optional[AgentPolicyAssignment]:
        stmt = (
            select(AgentPolicyAssignment)
            .where(AgentPolicyAssignment.agent_id == agent_id, AgentPolicyAssignment.is_active.is_(True))
            .limit(1)
        )
        return await self.session.scalar(stmt)

    async def assign_to_agent(self, agent_id: uuid.UUID, policy_id: uuid.UUID) -> AgentPolicyAssignment:
        # Check if existing assignment exists
        stmt = select(AgentPolicyAssignment).where(
            AgentPolicyAssignment.agent_id == agent_id,
            AgentPolicyAssignment.policy_id == policy_id,
        )
        existing = await self.session.scalar(stmt)
        if existing:
            existing.is_active = True
            await self.session.flush()
            return existing

        assignment = AgentPolicyAssignment(agent_id=agent_id, policy_id=policy_id, is_active=True)
        self.session.add(assignment)
        await self.session.flush()
        return assignment
