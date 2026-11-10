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


class AgentSpendingItem(BaseModel):
    agent_id: uuid.UUID
    agent_name: str
    total_spent: decimal.Decimal
    purchase_count: int


class SpendingSummaryResponse(BaseModel):
    total_spent: decimal.Decimal
    total_refunded: decimal.Decimal
    net_spent: decimal.Decimal
    currency: str = "USD"
    by_category: Dict[str, decimal.Decimal]
    by_supplier: Dict[str, decimal.Decimal]
    by_agent: List[AgentSpendingItem]


class AgentSummaryResponse(BaseModel):
    agent_id: uuid.UUID
    name: str
    is_active: bool
    assigned_policy_name: Optional[str]
    assigned_budget_allocated: Optional[decimal.Decimal]
    assigned_budget_spent: Optional[decimal.Decimal]
    total_purchases_requested: int
    total_purchases_approved: int
    total_purchases_completed: int
    total_spent: decimal.Decimal
    currency: str = "USD"
    created_at: datetime.datetime
