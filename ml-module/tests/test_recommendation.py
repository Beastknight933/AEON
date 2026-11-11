"""Unit tests for AEON ML quote recommendation engine."""

import pytest
from aeon_ml import (
    CriteriaWeights,
    ProcurementRequirements,
    RecommendationRequest,
    RecommendationResponse,
    SupplierAttributes,
    SupplierQuote,
    recommend,
)


@pytest.fixture
def sample_quotes():
    """Sample candidate quotes with differing trade-offs."""
    return [
        SupplierQuote(
            quote_id="Q-001",
            supplier_id="SUP-ALPHA",
            amount=12000.0,
            currency="USD",
            supplier_attributes=SupplierAttributes(
                delivery_days=10,
                quality_score=95.0,
                reliability_rating=92.0,
                on_time_delivery_rate=0.98,
            ),
        ),
        SupplierQuote(
            quote_id="Q-002",
            supplier_id="SUP-BETA",
            amount=9500.0,
            currency="USD",
            supplier_attributes=SupplierAttributes(
                delivery_days=14,
                quality_score=82.0,
                reliability_rating=85.0,
                on_time_delivery_rate=0.90,
            ),
        ),
        SupplierQuote(
            quote_id="Q-003",
            supplier_id="SUP-GAMMA",
            amount=10200.0,
            currency="USD",
            supplier_attributes=SupplierAttributes(
                delivery_days=7,
                quality_score=88.0,
                reliability_rating=90.0,
                on_time_delivery_rate=0.94,
            ),
        ),
    ]


def test_standard_recommendation_flow(sample_quotes):
    """Test standard recommendation with multi-attribute trade-offs."""
    request = RecommendationRequest(
        purchase_id="PO-REQ-2026-001",
        currency="USD",
        requirements=ProcurementRequirements(
            max_delivery_days=12,
            target_price=11000.0,
            min_quality_score=80.0,
        ),
        quotes=sample_quotes,
    )

    response = recommend(request)

    # 1. Output structure assertions
    assert isinstance(response, RecommendationResponse)
    assert response.purchase_id == "PO-REQ-2026-001"
    assert response.recommended_quote_id in ["Q-001", "Q-002", "Q-003"]
    assert len(response.scores) == 3
    assert len(response.reasoning) > 20

    # 2. Scores range assertions (documented 0.0 to 100.0)
    for score_item in response.scores:
        assert 0.0 <= score_item.composite_score <= 100.0
        assert 0.0 <= score_item.sub_scores.price_score <= 100.0
        assert 0.0 <= score_item.sub_scores.speed_score <= 100.0
        assert 0.0 <= score_item.sub_scores.quality_score <= 100.0
        assert 0.0 <= score_item.sub_scores.reliability_score <= 100.0

    # 3. Ranks ordered 1, 2, 3
    ranks = [s.rank for s in response.scores]
    assert ranks == [1, 2, 3]

    # 4. Top ranked quote matches recommended_quote_id
    assert response.scores[0].quote_id == response.recommended_quote_id


def test_speed_priority_weighting(sample_quotes):
    """When speed weight is high, fastest delivery quote (Q-003, 7 days) should win."""
    request = RecommendationRequest(
        purchase_id="PO-URGENT-002",
        currency="USD",
        requirements=ProcurementRequirements(
            max_delivery_days=8,
            priority_weights=CriteriaWeights(
                price_weight=0.10,
                speed_weight=0.60,
                quality_weight=0.15,
                reliability_weight=0.15,
            ),
        ),
        quotes=sample_quotes,
    )

    response = recommend(request)
    assert response.recommended_quote_id == "Q-003"
    # Q-002 has 14 days delivery, exceeding max 8 days, so it should incur penalties
    q2_metric = next(s for s in response.scores if s.quote_id == "Q-002")
    assert q2_metric.sub_scores.penalty_deduction > 0
    assert not q2_metric.meets_requirements


def test_cost_priority_weighting(sample_quotes):
    """When cost weight is dominant and all quotes meet delivery, lowest price wins."""
    request = RecommendationRequest(
        purchase_id="PO-COST-SAVING-003",
        currency="USD",
        requirements=ProcurementRequirements(
            max_delivery_days=20,  # All quotes meet this
            priority_weights=CriteriaWeights(
                price_weight=0.85,
                speed_weight=0.05,
                quality_weight=0.05,
                reliability_weight=0.05,
            ),
        ),
        quotes=sample_quotes,
    )

    response = recommend(request)
    assert response.recommended_quote_id == "Q-002"  # Q-002 is 9500.0 (lowest)


def test_single_quote_recommendation():
    """Edge case: Single candidate quote should always be recommended with valid metrics."""
    single_quote = SupplierQuote(
        quote_id="Q-SOLO",
        supplier_id="SUP-SOLO",
        amount=5000.0,
        currency="USD",
        supplier_attributes=SupplierAttributes(
            delivery_days=5,
            quality_score=90.0,
            reliability_rating=90.0,
        ),
    )
    request = RecommendationRequest(
        purchase_id="PO-SOLO-001",
        currency="USD",
        requirements=ProcurementRequirements(max_delivery_days=7),
        quotes=[single_quote],
    )

    response = recommend(request)
    assert response.recommended_quote_id == "Q-SOLO"
    assert len(response.scores) == 1
    assert response.scores[0].rank == 1
    assert 0.0 <= response.scores[0].composite_score <= 100.0
