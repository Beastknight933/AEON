import datetime
import uuid
from typing import Optional, List, Tuple
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.agent import Agent, AgentCredential
from app.core.security import verify_agent_key


class AgentRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, agent_id: uuid.UUID, org_id: Optional[uuid.UUID] = None) -> Optional[Agent]:
        stmt = select(Agent).where(Agent.id == agent_id)
        if org_id:
            stmt = stmt.where(Agent.organization_id == org_id)
        return await self.session.scalar(stmt)

    async def list_by_org(
        self, org_id: uuid.UUID, skip: int = 0, limit: int = 50, is_active: Optional[bool] = None
    ) -> List[Agent]:
        stmt = select(Agent).where(Agent.organization_id == org_id)
        if is_active is not None:
            stmt = stmt.where(Agent.is_active == is_active)
        stmt = stmt.order_by(Agent.created_at.desc()).offset(skip).limit(limit)
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def create(self, agent: Agent) -> Agent:
        self.session.add(agent)
        await self.session.flush()
        return agent

    async def update(self, agent: Agent) -> Agent:
        self.session.add(agent)
        await self.session.flush()
        return agent

    async def create_credential(self, credential: AgentCredential) -> AgentCredential:
        self.session.add(credential)
        await self.session.flush()
        return credential

    async def get_credentials_for_agent(self, agent_id: uuid.UUID) -> List[AgentCredential]:
        stmt = select(AgentCredential).where(
            AgentCredential.agent_id == agent_id
        ).order_by(AgentCredential.created_at.desc())
        result = await self.session.scalars(stmt)
        return list(result.all())

    async def revoke_all_credentials_for_agent(self, agent_id: uuid.UUID) -> int:
        now = datetime.datetime.now(datetime.timezone.utc)
        stmt = (
            update(AgentCredential)
            .where(AgentCredential.agent_id == agent_id, AgentCredential.is_revoked.is_(False))
            .values(is_revoked=True, revoked_at=now)
        )
        result = await self.session.execute(stmt)
        await self.session.flush()
        return result.rowcount

    async def revoke_credential_by_id(self, credential_id: uuid.UUID, org_id: uuid.UUID) -> Optional[AgentCredential]:
        stmt = select(AgentCredential).where(
            AgentCredential.id == credential_id,
            AgentCredential.organization_id == org_id,
        )
        cred = await self.session.scalar(stmt)
        if cred and not cred.is_revoked:
            cred.is_revoked = True
            cred.revoked_at = datetime.datetime.now(datetime.timezone.utc)
            await self.session.flush()
        return cred

    async def authenticate_by_raw_key(self, raw_key: str) -> Optional[Tuple[Agent, AgentCredential]]:
        """
        Authenticate an agent by raw API key.
        1. Extract prefix from key.
        2. Query non-revoked credentials with matching prefix.
        3. Constant-time verify the key against stored hash.
        4. Eagerly load and verify the active Agent.
        """
        if len(raw_key) < 16:
            return None

        prefix = raw_key[:16]
        stmt = select(AgentCredential).where(
            AgentCredential.key_prefix == prefix,
            AgentCredential.is_revoked.is_(False),
        )
        candidates = list((await self.session.scalars(stmt)).all())
        for candidate in candidates:
            if verify_agent_key(raw_key, candidate.key_hash):
                agent = await self.get_by_id(candidate.agent_id)
                if agent and agent.is_active:
                    return agent, candidate
        return None
