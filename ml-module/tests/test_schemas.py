"""Tests for Pydantic input and output schemas."""

import pytest
from pydantic import ValidationError
from aeon_ml import (
    CriteriaWeights,
    ProcurementRequirements,
    QuoteEvaluationMetric,
    RecommendationRequest,
    RecommendationResponse,
    ScoreBreakdown,
    SupplierAttributes,
    SupplierQuote,
)


def test_supplier_attributes_defaults_and_validation():
    attrs = SupplierAttributes(delivery_days=3)
    assert attrs.delivery_days == 3
    assert attrs.quality_score == 80.0
    assert attrs.reliability_rating == 80.0
    assert attrs.warranty_months == 12

    # Negative delivery days not permitted
    with pytest.raises(ValidationError):
        SupplierAttributes(delivery_days=0)


def test_supplier_quote_currency_normalization():
    quote = SupplierQuote(
        quote_id="Q-TEST",
        supplier_id="SUPP-1",
        amount=150.0,
        currency="  usd  ",  # Should be normalized to USD
        supplier_attributes=SupplierAttributes(delivery_days=5),
    )
    assert quote.currency == "USD"


def test_criteria_weights_normalization():
    weights = CriteriaWeights(
        price_weight=0.5,
        speed_weight=0.5,
        quality_weight=0.5,
        reliability_weight=0.5,
    )
    norm = weights.normalized()
    total = norm.price_weight + norm.speed_weight + norm.quality_weight + norm.reliability_weight
    assert pytest.approx(total, 0.001) == 1.0


def test_recommendation_response_invariant_detection():
    """Ensure RecommendationResponse rejects a recommended_quote_id not in scores."""
    breakdown = ScoreBreakdown(
        price_score=90.0,
        speed_score=90.0,
        quality_score=90.0,
        reliability_score=90.0,
    )
    score_metric = QuoteEvaluationMetric(
        quote_id="Q-REAL",
        supplier_id="SUP-REAL",
        amount=500.0,
        currency="USD",
        composite_score=90.0,
        rank=1,
        sub_scores=breakdown,
        meets_requirements=True,
    )

    # Valid response
    valid_resp = RecommendationResponse(
        purchase_id="PR-01",
        recommended_quote_id="Q-REAL",
        reasoning="Top score",
        scores=[score_metric],
    )
    assert valid_resp.recommended_quote_id == "Q-REAL"

    # Invalid response with invented quote ID
    with pytest.raises(ValidationError) as exc_info:
        RecommendationResponse(
            purchase_id="PR-01",
            recommended_quote_id="Q-INVENTED",  # Not in scores!
            reasoning="Top score",
            scores=[score_metric],
        )
    assert "Invariant violation" in str(exc_info.value)

