import decimal
import uuid
from typing import Dict, List
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApprovalStatus, PurchaseStatus, TransactionStatus, TransactionType
from app.models.agent import Agent
from app.models.approval import Approval
from app.models.audit import AuditEvent
from app.models.budget import Budget
from app.models.policy import AgentPolicyAssignment, Policy
from app.models.purchase import PurchaseRequest
from app.models.supplier import SupplierQuote
from app.models.transaction import Transaction
from app.schemas.dashboard import (
    AgentSpendingItem,
    AgentSummaryResponse,
    DashboardOverviewResponse,
    DashboardStatsResponse,
    RecentActivityItem,
    SpendingSummaryResponse,
)


class DashboardService:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_overview(self, organization_id: uuid.UUID) -> DashboardOverviewResponse:
        stats = await self.get_stats(organization_id)

        # Query recent 15 audit events
        stmt_audit = (
            select(AuditEvent)
            .where(AuditEvent.organization_id == organization_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(15)
        )
        events = list((await self.session.scalars(stmt_audit)).all())
        recent_activities = [RecentActivityItem.model_validate(e) for e in events]

        return DashboardOverviewResponse(stats=stats, recent_activities=recent_activities)

    async def get_stats(self, organization_id: uuid.UUID) -> DashboardStatsResponse:
        # 1. Agents stats
        stmt_agents = select(Agent).where(Agent.organization_id == organization_id)
        agents = list((await self.session.scalars(stmt_agents)).all())
        total_agents = len(agents)
        active_agents = sum(1 for a in agents if a.is_active)

        # 2. Budget stats
        stmt_budgets = select(Budget).where(
            Budget.organization_id == organization_id,
            Budget.is_active.is_(True),
        )
        budgets = list((await self.session.scalars(stmt_budgets)).all())
        total_allocated = sum((b.allocated_amount for b in budgets), decimal.Decimal("0.00"))
        total_spent = sum((b.spent_amount for b in budgets), decimal.Decimal("0.00"))
        total_reserved = sum((b.reserved_amount for b in budgets), decimal.Decimal("0.00"))
        total_available = total_allocated - total_spent - total_reserved

        # 3. Pending approvals
        stmt_approvals = (
            select(func.count(Approval.id))
            .join(PurchaseRequest, Approval.purchase_request_id == PurchaseRequest.id)
            .where(
                PurchaseRequest.organization_id == organization_id,
                Approval.status == ApprovalStatus.PENDING,
            )
        )
        pending_approvals = (await self.session.scalar(stmt_approvals)) or 0

        # 4. Purchases counts
        stmt_pr = select(PurchaseRequest).where(PurchaseRequest.organization_id == organization_id)
        all_pr = list((await self.session.scalars(stmt_pr)).all())
        total_pr = len(all_pr)
        completed_pr = sum(1 for p in all_pr if p.status == PurchaseStatus.COMPLETED)

        return DashboardStatsResponse(
            total_agents=total_agents,
            active_agents=active_agents,
            total_budget_allocated=total_allocated,
            total_budget_spent=total_spent,
            total_budget_reserved=total_reserved,
            total_budget_available=total_available,
            pending_approvals_count=pending_approvals,
            total_purchases_count=total_pr,
            completed_purchases_count=completed_pr,
            currency="USD",
        )

    async def get_spending_summary(self, organization_id: uuid.UUID) -> SpendingSummaryResponse:
        """
        Aggregate spending by category, supplier, and agent across settled transactions.
        """
        stmt_tx = (
            select(Transaction)
            .options(
                selectinload(Transaction.purchase_request).selectinload(PurchaseRequest.agent),
                selectinload(Transaction.purchase_request).selectinload(PurchaseRequest.selected_quote),
            )
            .where(
                Transaction.organization_id == organization_id,
                Transaction.status == TransactionStatus.SETTLED,
            )
        )
        txs = list((await self.session.scalars(stmt_tx)).all())

        by_category: Dict[str, decimal.Decimal] = {}
        by_supplier: Dict[str, decimal.Decimal] = {}
        agent_spend_map: Dict[uuid.UUID, dict] = {}
        total_spent = decimal.Decimal("0.00")
        total_refunded = decimal.Decimal("0.00")

        for tx in txs:
            if tx.type == TransactionType.PURCHASE:
                total_spent += tx.amount
                pr = tx.purchase_request
                if pr:
                    cat = pr.category or "uncategorized"
                    by_category[cat] = by_category.get(cat, decimal.Decimal("0.00")) + tx.amount

                    sup_name = pr.selected_quote.supplier_name if pr.selected_quote else "Unknown Supplier"
                    by_supplier[sup_name] = by_supplier.get(sup_name, decimal.Decimal("0.00")) + tx.amount

                    if pr.agent:
                        aid = pr.agent.id
                        if aid not in agent_spend_map:
                            agent_spend_map[aid] = {
                                "agent_id": aid,
                                "agent_name": pr.agent.name,
                                "total_spent": decimal.Decimal("0.00"),
                                "purchase_count": 0,
                            }
                        agent_spend_map[aid]["total_spent"] += tx.amount
                        agent_spend_map[aid]["purchase_count"] += 1
            elif tx.type == TransactionType.REFUND:
                total_refunded += tx.amount

        # Also query any refund transactions
        stmt_ref = select(Transaction).where(
            Transaction.organization_id == organization_id,
            Transaction.type == TransactionType.REFUND,
        )
        ref_txs = list((await self.session.scalars(stmt_ref)).all())
        for r_tx in ref_txs:
            if r_tx not in txs:
                total_refunded += r_tx.amount

        agent_items = [
            AgentSpendingItem(
                agent_id=v["agent_id"],
                agent_name=v["agent_name"],
                total_spent=v["total_spent"],
                purchase_count=v["purchase_count"],
            )
            for v in agent_spend_map.values()
        ]

        net_spent = max(decimal.Decimal("0.00"), total_spent - total_refunded)

        return SpendingSummaryResponse(
            total_spent=total_spent,
            total_refunded=total_refunded,
            net_spent=net_spent,
            currency="USD",
            by_category=by_category,
            by_supplier=by_supplier,
            by_agent=agent_items,
        )

    async def get_agent_summaries(self, organization_id: uuid.UUID) -> List[AgentSummaryResponse]:
        """
        Produce a comprehensive summary for every autonomous agent in the organization.
        """
        stmt_agents = (
            select(Agent)
            .options(
                selectinload(Agent.policy_assignments).selectinload(AgentPolicyAssignment.policy),
                selectinload(Agent.purchase_requests),
            )
            .where(Agent.organization_id == organization_id)
            .order_by(Agent.name.asc())
        )
        agents = list((await self.session.scalars(stmt_agents)).all())

        results: List[AgentSummaryResponse] = []
        for agent in agents:
            # Active policy
            active_assignment = next((a for a in agent.policy_assignments if a.is_active), None)
            policy_name = active_assignment.policy.name if active_assignment and active_assignment.policy else None

            # Dedicated agent budget
            stmt_b = select(Budget).where(
                Budget.organization_id == organization_id,
                Budget.agent_id == agent.id,
                Budget.is_active.is_(True),
            )
            agent_budget = await self.session.scalar(stmt_b)
            allocated = agent_budget.allocated_amount if agent_budget else None
            spent = agent_budget.spent_amount if agent_budget else None

            # Purchases counts
            prs = agent.purchase_requests
            requested_count = len(prs)
            approved_count = sum(1 for p in prs if p.status in (PurchaseStatus.AUTHORIZED, PurchaseStatus.COMPLETED))
            completed_count = sum(1 for p in prs if p.status == PurchaseStatus.COMPLETED)

            # Spent amount from settled transactions
            stmt_tx = (
                select(func.coalesce(func.sum(Transaction.amount), decimal.Decimal("0.00")))
                .join(PurchaseRequest, Transaction.purchase_request_id == PurchaseRequest.id)
                .where(
                    PurchaseRequest.agent_id == agent.id,
                    Transaction.type == TransactionType.PURCHASE,
                    Transaction.status == TransactionStatus.SETTLED,
                )
            )
            total_agent_spent = await self.session.scalar(stmt_tx) or decimal.Decimal("0.00")

            results.append(
                AgentSummaryResponse(
                    agent_id=agent.id,
                    name=agent.name,
                    is_active=agent.is_active,
                    assigned_policy_name=policy_name,
                    assigned_budget_allocated=allocated,
                    assigned_budget_spent=spent,
                    total_purchases_requested=requested_count,
                    total_purchases_approved=approved_count,
                    total_purchases_completed=completed_count,
                    total_spent=total_agent_spent,
                    currency="USD",
                    created_at=agent.created_at,
                )
            )

        return results
