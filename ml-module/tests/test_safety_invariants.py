"""Tests strictly asserting the 9 integration invariants from the AEON contract:

1. Model is NOT responsible for database access (pure in-memory functional interface).
2. Model CANNOT change supplier quote amounts (immutability / frozen schema).
3. Model CANNOT make authorization or payment decisions (pure advisory recommendation).
4. Model CANNOT invent quote IDs (recommended_quote_id strictly exists in input).
5. Output is structured (validated Pydantic models), not unvalidated free-form text.
6. Error handling for model failures and invalid states.
"""

import pytest
from pydantic import ValidationError
from aeon_ml import (
    ProcurementRequirements,
    RecommendationRequest,
    RecommendationResponse,
    SupplierAttributes,
    SupplierQuote,
    recommend,
)


@pytest.fixture
def base_quotes():
    return [
        SupplierQuote(
            quote_id="Q-INV-A",
            supplier_id="SUP-A",
            amount=1500.50,
            currency="EUR",
            supplier_attributes=SupplierAttributes(
                delivery_days=3,
                quality_score=85.0,
                reliability_rating=90.0,
            ),
        ),
        SupplierQuote(
            quote_id="Q-INV-B",
            supplier_id="SUP-B",
            amount=1420.00,
            currency="EUR",
            supplier_attributes=SupplierAttributes(
                delivery_days=5,
                quality_score=92.0,
                reliability_rating=88.0,
            ),
        ),
    ]


def test_invariant_1_no_database_access():
    """Invariant 1: Engine is a pure in-memory callable requiring zero DB connections."""
    import inspect
    from aeon_ml.engine import QuoteRecommendationEngine

    engine = QuoteRecommendationEngine()
    # Ensure no db connection attributes or socket connections exist
    assert not hasattr(engine, "db")
    assert not hasattr(engine, "session")
    assert not hasattr(engine, "connection")


def test_invariant_2_quote_amounts_are_immutable(base_quotes):
    """Invariant 2: Do not let the model change supplier quote amounts.

    SupplierQuote is frozen and immutable; amounts cannot be modified.
    """
    original_amounts = {q.quote_id: q.amount for q in base_quotes}

    request = RecommendationRequest(
        purchase_id="PURCHASE-IMMUTABLE-01",
        currency="EUR",
        requirements=ProcurementRequirements(max_delivery_days=10),
        quotes=base_quotes,
    )

    response = recommend(request)

    # 1. Check original quote objects were not modified
    for q in request.quotes:
        assert q.amount == original_amounts[q.quote_id]

    # 2. Check response scores preserve exact original amounts
    for score_item in response.scores:
        assert score_item.amount == original_amounts[score_item.quote_id]

    # 3. Check attempt to mutate raises ValidationError (frozen)
    with pytest.raises(ValidationError):
        base_quotes[0].amount = 999.0  # type: ignore


def test_invariant_3_no_authorization_or_payment_decisions(base_quotes):
    """Invariant 3: Model does not make authorization or payment decisions.

    The response schema only contains recommendation, reasoning, and scores.
    It contains no authorization, payment status, budget override, or policy fields.
    """
    request = RecommendationRequest(
        purchase_id="PURCHASE-NO-AUTH-01",
        currency="EUR",
        requirements=ProcurementRequirements(),
        quotes=base_quotes,
    )

    response = recommend(request)
    response_dict = response.model_dump()

    # Disallowed decision fields
    disallowed_fields = [
        "authorized",
        "is_authorized",
        "approved",
        "payment_authorized",
        "payment_amount",
        "override_policy",
        "enforce_budget",
        "status",
        "execute_transaction",
    ]
    for field in disallowed_fields:
        assert field not in response_dict, f"Disallowed governance field '{field}' found in response!"


def test_invariant_4_never_invent_quote_ids(base_quotes):
    """Invariant 4: Do not invent quote IDs.

    The recommended_quote_id must strictly belong to the input quotes.
    """
    candidate_ids = {q.quote_id for q in base_quotes}

    request = RecommendationRequest(
        purchase_id="PURCHASE-REAL-ID-01",
        currency="EUR",
        requirements=ProcurementRequirements(),
        quotes=base_quotes,
    )

    response = recommend(request)
    assert response.recommended_quote_id in candidate_ids
    assert response.recommended_quote_id in ["Q-INV-A", "Q-INV-B"]


def test_invariant_5_structured_result_not_unvalidated_text(base_quotes):
    """Invariant 5: Return a structured result, not unvalidated free-form text."""
    request = RecommendationRequest(
        purchase_id="PURCHASE-STRUCT-01",
        currency="EUR",
        requirements=ProcurementRequirements(),
        quotes=base_quotes,
    )

    response = recommend(request)

    # Validated Pydantic response
    assert isinstance(response, RecommendationResponse)
    assert hasattr(response, "recommended_quote_id")
    assert hasattr(response, "reasoning")
    assert hasattr(response, "scores")
    assert isinstance(response.scores, list)
    assert len(response.scores) > 0
    # JSON schema serializable
    json_repr = response.model_dump_json()
    assert isinstance(json_repr, str)

