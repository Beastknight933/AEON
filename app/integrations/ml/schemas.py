import decimal
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class QuoteCandidate(BaseModel):
    """
    Representation of a persisted supplier quote provided to the ML model.
    """
    quote_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_code: str
    supplier_name: str
    unit_price: decimal.Decimal = decimal.Decimal("0.00")
    quantity: int = 1
    total_amount: decimal.Decimal
    currency: str = "USD"
    estimated_delivery_days: int = 0
    reliability_score: decimal.Decimal = decimal.Decimal("1.00")
    attributes: Dict[str, Any] = Field(default_factory=dict)


class RecommendationRequest(BaseModel):
    """
    Structured request passed to the ML recommendation provider.
    """
    purchase_id: uuid.UUID
    currency: str = "USD"
    item_description: str
    category: str
    requirements: Dict[str, Any] = Field(default_factory=dict)
    candidates: List[QuoteCandidate] = Field(..., min_length=1)


class RecommendationResponse(BaseModel):
    """
    Structured decision returned by the recommendation provider.
    """
    recommended_quote_id: uuid.UUID
    reasoning: str = Field(..., min_length=1)
    comparison_scores: Dict[str, Any] = Field(default_factory=dict)
    provider_type: str = "mock"  # "mock", "module", "fallback"
    model_version: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
