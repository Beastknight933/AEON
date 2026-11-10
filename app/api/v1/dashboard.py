from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user_and_membership
from app.core.database import get_db
from app.models.organization import Membership, Organization, User
from app.schemas.dashboard import (
    DashboardOverviewResponse,
    DashboardStatsResponse,
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
