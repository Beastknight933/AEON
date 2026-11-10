import datetime
import decimal
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel


class DashboardStatsResponse(BaseModel):
    total_agents: int
    active_agents: int
    total_budget_allocated: decimal.Decimal
    total_budget_spent: decimal.Decimal
    total_budget_reserved: decimal.Decimal
    total_budget_available: decimal.Decimal
    pending_approvals_count: int
    total_purchases_count: int
    completed_purchases_count: int
    currency: str = "USD"


class RecentActivityItem(BaseModel):
    id: uuid.UUID
    actor_type: str
    actor_id: Optional[str]
    action: str
    entity_type: str
    entity_id: Optional[str]
    metadata_json: Dict[str, Any]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class DashboardOverviewResponse(BaseModel):
    stats: DashboardStatsResponse
    recent_activities: List[RecentActivityItem]
