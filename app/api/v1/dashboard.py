from typing import List
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_and_membership
from app.core.database import get_db
from app.models.organization import Membership, Organization, User
from app.schemas.dashboard import (
    AgentSummaryResponse,
    DashboardOverviewResponse,
    DashboardStatsResponse,
    SpendingSummaryResponse,
)
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["Dashboard & Metrics"])


@router.get("/overview", response_model=DashboardOverviewResponse)
async def get_dashboard_overview(
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Get consolidated dashboard metrics, KPI counters, and recent activity logs for the external frontend.
    """
    _, _, org = context
    service = DashboardService(db)
    return await service.get_overview(org.id)


@router.get("/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Get real-time agent, budget, approval, and purchase statistics.
    """
    _, _, org = context
    service = DashboardService(db)
    return await service.get_stats(org.id)


@router.get("/spending", response_model=SpendingSummaryResponse)
async def get_spending_summary(
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Get spending summaries aggregated by category, supplier, and agent.
    """
    _, _, org = context
    service = DashboardService(db)
    return await service.get_spending_summary(org.id)


@router.get("/agents", response_model=List[AgentSummaryResponse])
async def get_agent_summaries(
    context: tuple[User, Membership, Organization] = Depends(get_current_user_and_membership),
    db: AsyncSession = Depends(get_db),
):
    """
    Get performance and procurement activity summaries for every autonomous agent in the organization.
    """
    _, _, org = context
    service = DashboardService(db)
    return await service.get_agent_summaries(org.id)
