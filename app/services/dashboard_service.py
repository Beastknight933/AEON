import decimal
import uuid
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.constants import ApprovalStatus, PurchaseStatus
from app.models.agent import Agent
from app.models.approval import Approval
from app.models.audit import AuditEvent
from app.models.budget import Budget
from app.models.purchase import PurchaseRequest
from app.schemas.dashboard import (
    DashboardOverviewResponse,
    DashboardStatsResponse,
    RecentActivityItem,
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
