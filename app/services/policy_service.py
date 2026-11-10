import decimal
import uuid
from typing import List, Optional, Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.errors import NotFoundError
from app.engines.policy_engine import DeterministicPolicyEngine
from app.models.policy import Policy, PolicyVersion, AgentPolicyAssignment
from app.repositories.agent_repo import AgentRepository
from app.repositories.budget_repo import BudgetRepository
from app.repositories.policy_repo import PolicyRepository
from app.schemas.policy import (
    PolicyCreateRequest,
    PolicyDecision,
    PolicyEvaluationRequest,
    PolicyResponse,
    PolicyVersionCreate,
    PolicyVersionResponse,
    PolicyAssignmentResponse,
)


class PolicyService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.policy_repo = PolicyRepository(session)
        self.agent_repo = AgentRepository(session)

    async def create_policy(self, organization_id: uuid.UUID, req: PolicyCreateRequest) -> PolicyResponse:
        policy = Policy(
            organization_id=organization_id,
            name=req.name.strip(),
            description=req.description.strip() if req.description else None,
            is_active=True,
            current_version=1,
        )
        version = PolicyVersion(
            version=1,
            max_amount_per_transaction=req.max_amount_per_transaction,
            max_amount_per_day=req.max_amount_per_day,
            approval_threshold_amount=req.approval_threshold_amount,
            allowed_suppliers=req.allowed_suppliers,
            allowed_currencies=req.allowed_currencies,
        )
        created_policy = await self.policy_repo.create(policy, version)
        await self.session.commit()
        await self.session.refresh(created_policy)
        # Reload with versions
        loaded = await self.policy_repo.get_by_id(created_policy.id, org_id=organization_id)
        return PolicyResponse.model_validate(loaded)

    async def list_policies(self, organization_id: uuid.UUID) -> List[PolicyResponse]:
        policies = await self.policy_repo.list_by_org(organization_id)
        return [PolicyResponse.model_validate(p) for p in policies]

    async def get_policy(self, policy_id: uuid.UUID, organization_id: uuid.UUID) -> PolicyResponse:
        policy = await self.policy_repo.get_by_id(policy_id, org_id=organization_id)
        if not policy:
            raise NotFoundError("Policy", policy_id)
        return PolicyResponse.model_validate(policy)

    async def add_version(
        self, policy_id: uuid.UUID, organization_id: uuid.UUID, req: PolicyVersionCreate
    ) -> PolicyVersionResponse:
        policy = await self.policy_repo.get_by_id(policy_id, org_id=organization_id)
        if not policy:
            raise NotFoundError("Policy", policy_id)

        next_version = policy.current_version + 1
        version = PolicyVersion(
            policy_id=policy.id,
            version=next_version,
            max_amount_per_transaction=req.max_amount_per_transaction,
            max_amount_per_day=req.max_amount_per_day,
            approval_threshold_amount=req.approval_threshold_amount,
            allowed_suppliers=req.allowed_suppliers,
            allowed_currencies=req.allowed_currencies,
        )
        await self.policy_repo.add_version(version)
        policy.current_version = next_version
        await self.session.commit()
        await self.session.refresh(version)
        return PolicyVersionResponse.model_validate(version)

    async def assign_to_agent(
        self, agent_id: uuid.UUID, policy_id: uuid.UUID, organization_id: uuid.UUID
    ) -> PolicyAssignmentResponse:
        agent = await self.agent_repo.get_by_id(agent_id, org_id=organization_id)
        if not agent:
            raise NotFoundError("Agent", agent_id)

        policy = await self.policy_repo.get_by_id(policy_id, org_id=organization_id)
        if not policy:
            raise NotFoundError("Policy", policy_id)

        assignment = await self.policy_repo.assign_to_agent(agent.id, policy.id)
        await self.session.commit()
        await self.session.refresh(assignment)
        return PolicyAssignmentResponse.model_validate(assignment)

    async def get_active_assignment_for_agent(
        self, agent_id: uuid.UUID, organization_id: uuid.UUID
    ) -> Optional[PolicyAssignmentResponse]:
        agent = await self.agent_repo.get_by_id(agent_id, org_id=organization_id)
        if not agent:
            raise NotFoundError("Agent", agent_id)

        assignment = await self.policy_repo.get_active_assignment_for_agent(agent.id)
        if not assignment:
            return None
        return PolicyAssignmentResponse.model_validate(assignment)

    async def get_active_policy_for_agent(
        self, agent_id: uuid.UUID
    ) -> Tuple[Optional[Policy], Optional[PolicyVersion]]:
        assignment = await self.policy_repo.get_active_assignment_for_agent(agent_id)
        if not assignment:
            return None, None
        policy = await self.policy_repo.get_by_id(assignment.policy_id)
        if not policy or not policy.is_active:
            return None, None
        version = await self.policy_repo.get_latest_version(policy.id)
        return policy, version

    async def evaluate_for_agent(
        self, organization_id: uuid.UUID, req: PolicyEvaluationRequest
    ) -> PolicyDecision:
        agent = await self.agent_repo.get_by_id(req.agent_id, org_id=organization_id)
        if not agent:
            raise NotFoundError("Agent", req.agent_id)

        policy, policy_version = await self.get_active_policy_for_agent(agent.id)
        budget_repo = BudgetRepository(self.session)
        budget = await budget_repo.get_budget_for_agent_or_org(organization_id, agent.id)

        return DeterministicPolicyEngine.evaluate(
            agent=agent,
            policy=policy,
            policy_version=policy_version,
            budget=budget,
            supplier_code=req.supplier_code,
            amount=req.amount,
            currency=req.currency,
            daily_spent_and_reserved=req.daily_spent_and_reserved or decimal.Decimal("0.00"),
        )
