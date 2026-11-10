import datetime
import decimal
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
from app.core.constants import PurchaseStatus
from app.schemas.policy import PolicyDecision


class PurchaseSubmitRequest(BaseModel):
    item_description: str = Field(..., min_length=2, max_length=255)
    category: str = Field(..., min_length=2, max_length=64)
    max_budget: decimal.Decimal = Field(..., gt=0)
    currency: str = Field("USD", max_length=3)
    requirements: Dict[str, Any] = Field(default_factory=dict)


class SupplierQuoteResponse(BaseModel):
    id: uuid.UUID
    purchase_request_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_name: str
    item_id: str
    unit_price: decimal.Decimal
    quantity: int
    total_amount: decimal.Decimal
    currency: str
    estimated_delivery_days: int
    expires_at: Optional[datetime.datetime] = None
    is_valid: bool = True
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class RecommendationDetailResponse(BaseModel):
    id: uuid.UUID
    provider_type: str
    recommended_quote_id: uuid.UUID
    reasoning: str
    comparison_scores: Dict[str, Any]
    created_at: datetime.datetime

    class Config:
        from_attributes = True


class PurchaseDetailResponse(BaseModel):
    id: uuid.UUID
    organization_id: uuid.UUID
    agent_id: uuid.UUID
    item_description: str
    category: str
    max_budget: decimal.Decimal
    currency: str
    requirements: Dict[str, Any]
    status: PurchaseStatus
    selected_quote_id: Optional[uuid.UUID]
    quotes: List[SupplierQuoteResponse] = Field(default_factory=list)
    recommendation: Optional[RecommendationDetailResponse] = None
    policy_decision: Optional[PolicyDecision] = None
    created_at: datetime.datetime
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class PurchaseListResponse(BaseModel):
    id: uuid.UUID
    agent_id: uuid.UUID
    item_description: str
    category: str
    max_budget: decimal.Decimal
    currency: str
    status: PurchaseStatus
    selected_quote_id: Optional[uuid.UUID]
    created_at: datetime.datetime

    class Config:
        from_attributes = True
