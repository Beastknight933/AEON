import uuid
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.errors import NotFoundError
from app.core.security import generate_agent_api_key
from app.models.agent import Agent, AgentCredential
from app.repositories.agent_repo import AgentRepository
from app.schemas.agent import (
    AgentCreateRequest,
    AgentUpdateRequest,
    AgentKeyGenerateResponse,
    AgentResponse,
    AgentCreatedWithKeyResponse,
    AgentCredentialResponse,
)


class AgentService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.agent_repo = AgentRepository(session)

    async def create_agent_with_key(
        self, organization_id: uuid.UUID, req: AgentCreateRequest
    ) -> AgentCreatedWithKeyResponse:
        agent = Agent(
            organization_id=organization_id,
            name=req.name.strip(),
            description=req.description.strip() if req.description else None,
            is_active=True,
        )
        await self.agent_repo.create(agent)

        raw_key, prefix, key_hash = generate_agent_api_key()
        credential = AgentCredential(
            agent_id=agent.id,
            organization_id=organization_id,
            key_prefix=prefix,
            key_hash=key_hash,
            is_revoked=False,
        )
        await self.agent_repo.create_credential(credential)
        await self.session.commit()
        await self.session.refresh(agent)
        await self.session.refresh(credential)

        return AgentCreatedWithKeyResponse(
            agent=AgentResponse.model_validate(agent),
            credentials=AgentKeyGenerateResponse(
                credential_id=credential.id,
                agent_id=agent.id,
                raw_api_key=raw_key,
                key_prefix=prefix,
                created_at=credential.created_at,
            ),
        )

    async def list_agents(
        self, organization_id: uuid.UUID, skip: int = 0, limit: int = 50, is_active: Optional[bool] = None
    ) -> List[AgentResponse]:
        agents = await self.agent_repo.list_by_org(organization_id, skip=skip, limit=limit, is_active=is_active)
        return [AgentResponse.model_validate(a) for a in agents]

    async def get_agent(self, agent_id: uuid.UUID, organization_id: uuid.UUID) -> AgentResponse:
        agent = await self.agent_repo.get_by_id(agent_id, org_id=organization_id)
        if not agent:
            raise NotFoundError("Agent", agent_id)
        return AgentResponse.model_validate(agent)

    async def update_agent(
        self, agent_id: uuid.UUID, organization_id: uuid.UUID, req: AgentUpdateRequest
    ) -> AgentResponse:
        agent = await self.agent_repo.get_by_id(agent_id, org_id=organization_id)
        if not agent:
            raise NotFoundError("Agent", agent_id)

        if req.name is not None:
            agent.name = req.name.strip()
        if req.description is not None:
            agent.description = req.description.strip()
        if req.is_active is not None:
            agent.is_active = req.is_active

        await self.agent_repo.update(agent)
        await self.session.commit()
        await self.session.refresh(agent)
        return AgentResponse.model_validate(agent)

    async def rotate_agent_key(
        self, agent_id: uuid.UUID, organization_id: uuid.UUID
    ) -> AgentKeyGenerateResponse:
        agent = await self.agent_repo.get_by_id(agent_id, org_id=organization_id)
        if not agent:
            raise NotFoundError("Agent", agent_id)

        # Revoke old credentials
        await self.agent_repo.revoke_all_credentials_for_agent(agent_id)

        # Generate new credentials
        raw_key, prefix, key_hash = generate_agent_api_key()
        credential = AgentCredential(
            agent_id=agent.id,
            organization_id=organization_id,
            key_prefix=prefix,
            key_hash=key_hash,
            is_revoked=False,
        )
        await self.agent_repo.create_credential(credential)
        await self.session.commit()
        await self.session.refresh(credential)

        return AgentKeyGenerateResponse(
            credential_id=credential.id,
            agent_id=agent.id,
            raw_api_key=raw_key,
            key_prefix=prefix,
            created_at=credential.created_at,
        )

    async def revoke_credential(
        self, credential_id: uuid.UUID, organization_id: uuid.UUID
    ) -> AgentCredentialResponse:
        cred = await self.agent_repo.revoke_credential_by_id(credential_id, organization_id)
        if not cred:
            raise NotFoundError("AgentCredential", credential_id)
        await self.session.commit()
        await self.session.refresh(cred)
        return AgentCredentialResponse.model_validate(cred)

    async def list_agent_credentials(
        self, agent_id: uuid.UUID, organization_id: uuid.UUID
    ) -> List[AgentCredentialResponse]:
        agent = await self.agent_repo.get_by_id(agent_id, org_id=organization_id)
        if not agent:
            raise NotFoundError("Agent", agent_id)
        creds = await self.agent_repo.get_credentials_for_agent(agent_id)
        return [AgentCredentialResponse.model_validate(c) for c in creds]
