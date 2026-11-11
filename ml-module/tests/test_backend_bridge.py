"""Tests verifying compatibility with AEON backend `ModuleRecommendationAdapter` schemas."""

import decimal
import uuid
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field

from aeon_ml import recommend


class BackendQuoteCandidate(BaseModel):
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


class BackendRecommendationRequest(BaseModel):
    purchase_id: uuid.UUID
    currency: str = "USD"
    item_description: str
    category: str
    requirements: Dict[str, Any] = Field(default_factory=dict)
    candidates: List[BackendQuoteCandidate] = Field(..., min_length=1)


class BackendRecommendationResponse(BaseModel):
    recommended_quote_id: uuid.UUID
    reasoning: str = Field(..., min_length=1)
    comparison_scores: Dict[str, Any] = Field(default_factory=dict)
    provider_type: str = "mock"
    model_version: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)


def test_backend_module_adapter_compatibility():
    q1_id = uuid.uuid4()
    q2_id = uuid.uuid4()
    backend_req = BackendRecommendationRequest(
        purchase_id=uuid.uuid4(),
        currency="USD",
        item_description="Enterprise cloud GPU nodes",
        category="compute",
        requirements={"max_delivery_days": 7, "budget": 6000.0},
        candidates=[
            BackendQuoteCandidate(
                quote_id=q1_id,
                supplier_id=uuid.uuid4(),
                supplier_code="SUP-CLOUD-1",
                supplier_name="CloudOne",
                unit_price=decimal.Decimal("2500.00"),
                quantity=2,
                total_amount=decimal.Decimal("5000.00"),
                currency="USD",
                estimated_delivery_days=3,
                reliability_score=decimal.Decimal("0.96"),
                attributes={"quality_score": 92.0, "esg_score": 85.0},
            ),
            BackendQuoteCandidate(
                quote_id=q2_id,
                supplier_id=uuid.uuid4(),
                supplier_code="SUP-CLOUD-2",
                supplier_name="BudgetHost",
                unit_price=decimal.Decimal("2300.00"),
                quantity=2,
                total_amount=decimal.Decimal("4600.00"),
                currency="USD",
                estimated_delivery_days=14,
                reliability_score=decimal.Decimal("0.78"),
                attributes={"quality_score": 75.0},
            ),
        ],
    )

    raw_result = recommend(backend_req)
    validated = BackendRecommendationResponse.model_validate(raw_result)

    assert validated.recommended_quote_id == q1_id
    assert validated.provider_type == "module"
    assert validated.model_version == "aeon-ml-hybrid-v1.1.0"
    assert str(q1_id) in validated.comparison_scores["ranking"]
    assert str(q2_id) in validated.comparison_scores["ranking"]
    assert 0.0 <= validated.comparison_scores["best_composite_score"] <= 1.0
    assert 0.0 <= validated.comparison_scores["best_composite_score_100"] <= 100.0
