import datetime
import decimal
import uuid
from typing import List, Optional, Tuple
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import (
    ApprovalStatus,
    AuditAction,
    PurchaseStatus,
    ReservationStatus,
)
from app.core.errors import NotFoundError, StateTransitionError, SupplierError
from app.core.logging import get_logger
from app.engines.policy_engine import DeterministicPolicyEngine
from app.integrations.ml.module_adapter import get_recommendation_provider
from app.integrations.ml.schemas import QuoteCandidate, RecommendationRequest
from app.integrations.suppliers.registry import supplier_registry
from app.models.agent import Agent
from app.models.approval import Approval
from app.models.audit import AuditEvent
from app.models.budget import Budget, BudgetReservation
from app.models.organization import Organization
from app.models.purchase import PurchaseRequest
from app.models.recommendation import Recommendation
from app.models.supplier import Supplier, SupplierQuote
from app.repositories.budget_repo import BudgetRepository
from app.repositories.policy_repo import PolicyRepository
from app.schemas.policy import PolicyDecision
from app.schemas.purchase import (
    PurchaseDetailResponse,
    PurchaseListResponse,
    PurchaseSubmitRequest,
    RecommendationDetailResponse,
    SupplierQuoteResponse,
)

logger = get_logger("aeon.procurement")

# Explicit valid state transitions
VALID_PURCHASE_TRANSITIONS = {
    PurchaseStatus.REQUESTED: {PurchaseStatus.QUOTING, PurchaseStatus.CANCELLED},
    PurchaseStatus.QUOTING: {PurchaseStatus.RECOMMENDED, PurchaseStatus.BLOCKED, PurchaseStatus.CANCELLED},
    PurchaseStatus.RECOMMENDED: {
        PurchaseStatus.REQUIRES_APPROVAL,
        PurchaseStatus.AUTHORIZED,
        PurchaseStatus.BLOCKED,
        PurchaseStatus.CANCELLED,
    },
    PurchaseStatus.REQUIRES_APPROVAL: {PurchaseStatus.AUTHORIZED, PurchaseStatus.CANCELLED},
    PurchaseStatus.AUTHORIZED: {PurchaseStatus.COMPLETED, PurchaseStatus.CANCELLED},
    PurchaseStatus.BLOCKED: set(),
    PurchaseStatus.CANCELLED: set(),
    PurchaseStatus.COMPLETED: set(),
}


def transition_purchase_status(pr: PurchaseRequest, target_status: PurchaseStatus) -> None:
    allowed = VALID_PURCHASE_TRANSITIONS.get(pr.status, set())
    if target_status not in allowed:
        raise StateTransitionError(
            current_state=pr.status.value,
            attempted_state=target_status.value,
            entity="PurchaseRequest",
        )
    pr.status = target_status


class ProcurementService:
    def __init__(self, session: AsyncSession):
        self.session = session
        self.budget_repo = BudgetRepository(session)
        self.policy_repo = PolicyRepository(session)

    async def get_daily_spent_and_reserved(self, agent_id: uuid.UUID) -> decimal.Decimal:
        """
        Calculate total spent and reserved amounts for this agent in the past 24 hours.
        """
        since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=24)
        stmt = (
            select(func.coalesce(func.sum(BudgetReservation.amount), decimal.Decimal("0.00")))
            .join(PurchaseRequest, BudgetReservation.purchase_request_id == PurchaseRequest.id)
            .where(
                PurchaseRequest.agent_id == agent_id,
                BudgetReservation.status.in_([ReservationStatus.ACTIVE, ReservationStatus.SETTLED]),
                BudgetReservation.created_at >= since,
            )
        )
        total_res = await self.session.scalar(stmt) or decimal.Decimal("0.00")
        return total_res

    async def execute_procurement_pipeline(
        self,
        agent: Agent,
        organization: Organization,
        req: PurchaseSubmitRequest,
    ) -> PurchaseDetailResponse:
        """
        End-to-end 10-step agent procurement pipeline:
        1. Authenticate agent (caller dependency).
        2. Create purchase request (REQUESTED).
        3. Collect quotes from suppliers (QUOTING).
        4. Normalize & persist quotes.
        5. Request ML recommendation (RECOMMENDED).
        6. Validate recommendation against persisted quotes.
        7. Deterministic policy evaluation.
        8. Check and reserve budget.
        9. Create approval if required.
        10. Authorize when all conditions satisfied.
        """
        # Step 2: Create Purchase Request
        pr = PurchaseRequest(
            organization_id=organization.id,
            agent_id=agent.id,
            item_description=req.item_description.strip(),
            category=req.category.strip(),
            max_budget=req.max_budget,
            currency=req.currency.upper(),
            requirements=req.requirements,
            status=PurchaseStatus.REQUESTED,
        )
        self.session.add(pr)
        await self.session.flush()

        # Audit: Purchase Requested
        self.session.add(
            AuditEvent(
                organization_id=organization.id,
                actor_type="AGENT",
                actor_id=str(agent.id),
                action=AuditAction.PURCHASE_REQUESTED.value,
                entity_type="purchase_request",
                entity_id=str(pr.id),
                metadata_json={"max_budget": str(req.max_budget), "currency": req.currency},
            )
        )

        # Step 3 & 4: Collect and persist supplier quotes
        transition_purchase_status(pr, PurchaseStatus.QUOTING)
        supplier_models = await supplier_registry.ensure_suppliers_in_db(self.session)
        normalized_quotes = await supplier_registry.collect_quotes(
            item_description=pr.item_description,
            category=pr.category,
            requirements=pr.requirements,
            currency=pr.currency,
        )

        if not normalized_quotes:
            transition_purchase_status(pr, PurchaseStatus.BLOCKED)
            self.session.add(
                AuditEvent(
                    organization_id=organization.id,
                    actor_type="SYSTEM",
                    actor_id="supplier_registry",
                    action=AuditAction.POLICY_EVALUATED.value,
                    entity_type="purchase_request",
                    entity_id=str(pr.id),
                    metadata_json={"error": "NO_SUPPLIER_QUOTES"},
                )
            )
            await self.session.commit()
            raise SupplierError("No quotes could be obtained from registered suppliers.")

        now = datetime.datetime.now(datetime.timezone.utc)
        persisted_quotes: List[SupplierQuote] = []
        for nq in normalized_quotes:
            supp_model = supplier_models.get(nq.supplier_code)
            if not supp_model:
                continue
            is_valid = not nq.is_expired
            sq = SupplierQuote(
                purchase_request_id=pr.id,
                supplier_id=supp_model.id,
                supplier_name=nq.supplier_name,
                item_id=nq.item_id,
                unit_price=nq.unit_price,
                quantity=nq.quantity,
                total_amount=nq.total_amount,
                currency=nq.currency,
                estimated_delivery_days=nq.estimated_delivery_days,
                raw_quote_data=nq.raw_data,
                expires_at=nq.expires_at,
                is_valid=is_valid,
            )
            self.session.add(sq)
            persisted_quotes.append(sq)

        await self.session.flush()

        # Filter valid, unexpired candidates
        valid_candidates = [
            sq for sq in persisted_quotes
            if sq.is_valid and (sq.expires_at is None or sq.expires_at > now)
        ]

        if not valid_candidates:
            transition_purchase_status(pr, PurchaseStatus.BLOCKED)
            self.session.add(
                AuditEvent(
                    organization_id=organization.id,
                    actor_type="SYSTEM",
                    actor_id="procurement_pipeline",
                    action=AuditAction.POLICY_EVALUATED.value,
                    entity_type="purchase_request",
                    entity_id=str(pr.id),
                    metadata_json={"error": "ALL_QUOTES_EXPIRED_OR_INVALID"},
                )
            )
            await self.session.commit()
            return await self.get_purchase_detail(pr.id, organization.id)

        # Step 5: Request ML Recommendation
        transition_purchase_status(pr, PurchaseStatus.RECOMMENDED)
        candidates = [
            QuoteCandidate(
                quote_id=sq.id,
                supplier_id=sq.supplier_id,
                supplier_code=next(
                    (code for code, s in supplier_models.items() if s.id == sq.supplier_id), ""
                ),
                supplier_name=sq.supplier_name,
                total_amount=sq.total_amount,
                currency=sq.currency,
                estimated_delivery_days=sq.estimated_delivery_days,
                reliability_score=next(
                    (s.reliability_score for s in supplier_models.values() if s.id == sq.supplier_id),
                    decimal.Decimal("1.00"),
                ),
                attributes=sq.raw_quote_data,
            )
            for sq in valid_candidates
        ]

        rec_req = RecommendationRequest(
            purchase_id=pr.id,
            currency=pr.currency,
            item_description=pr.item_description,
            category=pr.category,
            requirements=pr.requirements,
            candidates=candidates,
        )

        provider = get_recommendation_provider()
        rec_res = await provider.recommend(rec_req)

        # Step 6: Validate recommendation against valid persisted quotes
        # "Never use model-provided amounts as payment amounts. Always load the selected quote from the database."
        selected_quote = next(
            (q for q in valid_candidates if q.id == rec_res.recommended_quote_id), None
        )
        if not selected_quote:
            # Fallback to the lowest amount valid quote if model returned an unverified/expired quote ID
            selected_quote = min(valid_candidates, key=lambda q: q.total_amount)
            rec_res.recommended_quote_id = selected_quote.id
            rec_res.reasoning = (
                f"[UNVERIFIED_QUOTE_FALLBACK: Model returned unknown/expired quote id] Defaulted to lowest-price valid quote from {selected_quote.supplier_name}."
            )

        pr.selected_quote_id = selected_quote.id

        recommendation_record = Recommendation(
            purchase_request_id=pr.id,
            provider_type=rec_res.provider_type,
            recommended_quote_id=selected_quote.id,
            reasoning=rec_res.reasoning,
            comparison_scores=rec_res.comparison_scores,
            is_accepted=True,
        )
        self.session.add(recommendation_record)
        await self.session.flush()

        # Step 7: Evaluate Deterministic Policy
        policy_assignment = await self.policy_repo.get_active_assignment_for_agent(agent.id)
        policy = None
        policy_version = None
        if policy_assignment:
            policy = await self.policy_repo.get_by_id(policy_assignment.policy_id)
            if policy:
                policy_version = await self.policy_repo.get_latest_version(policy.id)

        budget = await self.budget_repo.get_budget_for_agent_or_org(organization.id, agent.id)
        daily_spent = await self.get_daily_spent_and_reserved(agent.id)

        # Find supplier code of selected quote
        supplier_code = next(
            (code for code, s in supplier_models.items() if s.id == selected_quote.supplier_id), ""
        )

        decision: PolicyDecision = DeterministicPolicyEngine.evaluate(
            agent=agent,
            policy=policy,
            policy_version=policy_version,
            budget=budget,
            quote=selected_quote,
            supplier_code=supplier_code,
            daily_spent_and_reserved=daily_spent,
        )

        # Audit: Policy Evaluated
        self.session.add(
            AuditEvent(
                organization_id=organization.id,
                actor_type="SYSTEM",
                actor_id="policy_engine",
                action=AuditAction.POLICY_EVALUATED.value,
                entity_type="purchase_request",
                entity_id=str(pr.id),
                metadata_json={
                    "allowed": decision.allowed,
                    "requires_approval": decision.requires_approval,
                    "reason_codes": decision.reason_codes,
                },
            )
        )

        if not decision.allowed:
            transition_purchase_status(pr, PurchaseStatus.BLOCKED)
            await self.session.commit()
            return await self.get_purchase_detail(pr.id, organization.id, decision=decision)

        # Step 8: Check and reserve budget atomically
        assert budget is not None
        await self.budget_repo.reserve_funds_atomic(
            budget_id=budget.id,
            purchase_request_id=pr.id,
            amount=selected_quote.total_amount,
            currency=selected_quote.currency,
        )

        # Step 9 & 10: Human Approval Workflow or Direct Authorization
        if decision.requires_approval:
            transition_purchase_status(pr, PurchaseStatus.REQUIRES_APPROVAL)
            approval = Approval(
                purchase_request_id=pr.id,
                status=ApprovalStatus.PENDING,
                notes="Automated approval requirement triggered by spending threshold.",
            )
            self.session.add(approval)
            self.session.add(
                AuditEvent(
                    organization_id=organization.id,
                    actor_type="SYSTEM",
                    actor_id="procurement_pipeline",
                    action=AuditAction.APPROVAL_REQUESTED.value,
                    entity_type="approval",
                    entity_id=str(pr.id),
                    metadata_json={"amount": str(selected_quote.total_amount)},
                )
            )
        else:
            transition_purchase_status(pr, PurchaseStatus.AUTHORIZED)

        await self.session.commit()
        return await self.get_purchase_detail(pr.id, organization.id, decision=decision)

    async def get_purchase_detail(
        self,
        purchase_id: uuid.UUID,
        organization_id: uuid.UUID,
        decision: Optional[PolicyDecision] = None,
    ) -> PurchaseDetailResponse:
        stmt = (
            select(PurchaseRequest)
            .options(
                selectinload(PurchaseRequest.quotes),
                selectinload(PurchaseRequest.recommendations),
            )
            .where(
                PurchaseRequest.id == purchase_id,
                PurchaseRequest.organization_id == organization_id,
            )
        )
        pr = await self.session.scalar(stmt)
        if not pr:
            raise NotFoundError("PurchaseRequest", purchase_id)

        rec_detail = None
        if pr.recommendations:
            rec = pr.recommendations[-1]
            rec_detail = RecommendationDetailResponse.model_validate(rec)

        quotes_response = [SupplierQuoteResponse.model_validate(q) for q in pr.quotes]

        return PurchaseDetailResponse(
            id=pr.id,
            organization_id=pr.organization_id,
            agent_id=pr.agent_id,
            item_description=pr.item_description,
            category=pr.category,
            max_budget=pr.max_budget,
            currency=pr.currency,
            requirements=pr.requirements,
            status=pr.status,
            selected_quote_id=pr.selected_quote_id,
            quotes=quotes_response,
            recommendation=rec_detail,
            policy_decision=decision,
            created_at=pr.created_at,
            updated_at=pr.updated_at,
        )

    async def list_purchases(
        self,
        organization_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
        status: Optional[PurchaseStatus] = None,
    ) -> List[PurchaseListResponse]:
        stmt = select(PurchaseRequest).where(PurchaseRequest.organization_id == organization_id)
        if status:
            stmt = stmt.where(PurchaseRequest.status == status)
        stmt = stmt.order_by(PurchaseRequest.created_at.desc()).offset(skip).limit(limit)
        results = await self.session.scalars(stmt)
        return [PurchaseListResponse.model_validate(r) for r in results]
