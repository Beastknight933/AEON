"""Tests for error handling, business validation rules, and model failure modes."""

import pytest
from pydantic import ValidationError
from aeon_ml import (
    CurrencyMismatchError,
    DuplicateQuoteIdError,
    EmptyQuotesError,
    ModelInferenceError,
    ProcurementRequirements,
    QuoteRecommendationEngine,
    RecommendationRequest,
    SupplierAttributes,
    SupplierQuote,
    recommend,
)


def test_empty_quotes_list_raises_error():
    """Empty list of candidate quotes must be rejected during validation."""
    with pytest.raises(ValidationError) as exc_info:
        RecommendationRequest(
            purchase_id="REQ-EMPTY-01",
            currency="USD",
            requirements=ProcurementRequirements(),
            quotes=[],
        )
    assert "cannot be empty" in str(exc_info.value)


def test_currency_mismatch_raises_error():
    """Quotes with currency differing from request currency must be rejected."""
    mismatched_quotes = [
        SupplierQuote(
            quote_id="Q-USD-1",
            supplier_id="SUP-1",
            amount=100.0,
            currency="USD",
            supplier_attributes=SupplierAttributes(delivery_days=2),
        ),
        SupplierQuote(
            quote_id="Q-EUR-2",
            supplier_id="SUP-2",
            amount=90.0,
            currency="EUR",  # Mismatch!
            supplier_attributes=SupplierAttributes(delivery_days=3),
        ),
    ]

    with pytest.raises(ValidationError) as exc_info:
        RecommendationRequest(
            purchase_id="REQ-CURR-01",
            currency="USD",
            requirements=ProcurementRequirements(),
            quotes=mismatched_quotes,
        )
    assert "Currency mismatch detected" in str(exc_info.value)
    assert "EUR" in str(exc_info.value)


def test_duplicate_quote_ids_raises_error():
    """Duplicate quote IDs must be rejected."""
    dup_quotes = [
        SupplierQuote(
            quote_id="Q-DUP-01",
            supplier_id="SUP-1",
            amount=500.0,
            currency="USD",
            supplier_attributes=SupplierAttributes(delivery_days=5),
        ),
        SupplierQuote(
            quote_id="Q-DUP-01",  # Duplicate!
            supplier_id="SUP-2",
            amount=480.0,
            currency="USD",
            supplier_attributes=SupplierAttributes(delivery_days=4),
        ),
    ]

    with pytest.raises(ValidationError) as exc_info:
        RecommendationRequest(
            purchase_id="REQ-DUP-01",
            currency="USD",
            requirements=ProcurementRequirements(),
            quotes=dup_quotes,
        )
    assert "Duplicate quote IDs detected" in str(exc_info.value)


def test_engine_empty_quotes_guard():
    """Directly test engine guard for empty quotes raises EmptyQuotesError."""
    from aeon_ml.engine import QuoteRecommendationEngine
    engine = QuoteRecommendationEngine()

    # Construct request bypassing Pydantic validator to test engine runtime defense
    mock_request = type("MockRequest", (), {"quotes": []})()
    with pytest.raises(EmptyQuotesError):
        engine.recommend(mock_request)  # type: ignore


def test_negative_or_zero_amount_rejected():
    """Quote amount must be strictly positive."""
    with pytest.raises(ValidationError):
        SupplierQuote(
            quote_id="Q-ZERO",
            supplier_id="SUP-1",
            amount=0.0,
            currency="USD",
            supplier_attributes=SupplierAttributes(delivery_days=5),
        )

    with pytest.raises(ValidationError):
        SupplierQuote(
            quote_id="Q-NEG",
            supplier_id="SUP-1",
            amount=-50.0,
            currency="USD",
            supplier_attributes=SupplierAttributes(delivery_days=5),
        )


def test_identical_quotes_graceful_handling():
    """Edge case: Multiple quotes with identical amounts and attributes should not cause division by zero."""
    identical_quotes = [
        SupplierQuote(
            quote_id="Q-IDENT-1",
            supplier_id="SUP-A",
            amount=1000.0,
            currency="USD",
            supplier_attributes=SupplierAttributes(delivery_days=5, quality_score=80.0, reliability_rating=80.0),
        ),
        SupplierQuote(
            quote_id="Q-IDENT-2",
            supplier_id="SUP-B",
            amount=1000.0,
            currency="USD",
            supplier_attributes=SupplierAttributes(delivery_days=5, quality_score=80.0, reliability_rating=80.0),
        ),
    ]

    request = RecommendationRequest(
        purchase_id="REQ-IDENT-01",
        currency="USD",
        requirements=ProcurementRequirements(),
        quotes=identical_quotes,
    )

    response = recommend(request)
    assert response.recommended_quote_id in ["Q-IDENT-1", "Q-IDENT-2"]
    assert response.scores[0].composite_score == response.scores[1].composite_score


def test_non_finite_amount_rejected():
    """NaN and Inf amounts must be rejected during schema validation."""
    for bad_amount in (float("nan"), float("inf"), float("-inf")):
        with pytest.raises(ValidationError):
            SupplierQuote(
                quote_id="Q-BAD-FLOAT",
                supplier_id="SUP-1",
                amount=bad_amount,
                currency="USD",
                supplier_attributes=SupplierAttributes(delivery_days=3),
            )


def test_unexpected_ranker_failure_wrapped_in_model_inference_error():
    """Unexpected internal failures must be wrapped cleanly as ModelInferenceError."""

    class FailingRanker:
        version = "failing-test-ranker"

        def evaluate_quotes(self, quotes, requirements):
            raise RuntimeError("Simulated internal scoring crash")

    engine = QuoteRecommendationEngine(ranker=FailingRanker())  # type: ignore
    request = RecommendationRequest(
        purchase_id="REQ-FAIL-01",
        currency="USD",
        requirements=ProcurementRequirements(),
        quotes=[
            SupplierQuote(
                quote_id="Q-1",
                supplier_id="SUP-1",
                amount=250.0,
                currency="USD",
                supplier_attributes=SupplierAttributes(delivery_days=4),
            )
        ],
    )

    with pytest.raises(ModelInferenceError) as exc_info:
        engine.recommend(request)
    assert "Simulated internal scoring crash" in str(exc_info.value)
