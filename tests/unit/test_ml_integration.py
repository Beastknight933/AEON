import asyncio
import decimal
import sys
import types
import uuid
import pytest
from pydantic import ValidationError

from app.integrations.ml.base import RecommendationProvider
from app.integrations.ml.mock_provider import MockRecommendationProvider
from app.integrations.ml.module_adapter import ModuleRecommendationAdapter
from app.integrations.ml.schemas import QuoteCandidate, RecommendationRequest, RecommendationResponse


def make_dummy_candidates(num: int = 2) -> list[QuoteCandidate]:
    candidates = []
    prices = [decimal.Decimal("120.00"), decimal.Decimal("90.00"), decimal.Decimal("150.00")]
    reliabilities = [decimal.Decimal("0.98"), decimal.Decimal("0.90"), decimal.Decimal("0.95")]
    delays = [0, 3, 1]

    for i in range(num):
        candidates.append(
            QuoteCandidate(
                quote_id=uuid.uuid4(),
                supplier_id=uuid.uuid4(),
                supplier_code=f"supp_{i}",
                supplier_name=f"Supplier {i}",
                unit_price=prices[i % len(prices)],
                quantity=1,
                total_amount=prices[i % len(prices)],
                currency="USD",
                estimated_delivery_days=delays[i % len(delays)],
                reliability_score=reliabilities[i % len(reliabilities)],
                attributes={"tier": "standard"},
            )
        )
    return candidates


def make_dummy_request(candidates: list[QuoteCandidate] | None = None) -> RecommendationRequest:
    return RecommendationRequest(
        purchase_id=uuid.uuid4(),
        currency="USD",
        item_description="Test compute node",
        category="compute",
        requirements={"quantity": 1},
        candidates=candidates or make_dummy_candidates(2),
    )


@pytest.mark.asyncio
async def test_mock_provider_heuristics_and_ranking():
    provider = MockRecommendationProvider()
    candidates = make_dummy_candidates(3)
    req = make_dummy_request(candidates)

    res = await provider.recommend(req)
    assert isinstance(res, RecommendationResponse)
    assert res.provider_type == "mock"
    assert res.recommended_quote_id in [c.quote_id for c in candidates]
    assert len(res.reasoning) > 10
    assert "ranking" in res.comparison_scores
    assert res.comparison_scores["best_composite_score"] > 0


@pytest.mark.asyncio
async def test_mock_provider_single_candidate():
    provider = MockRecommendationProvider()
    candidates = make_dummy_candidates(1)
    req = make_dummy_request(candidates)

    res = await provider.recommend(req)
    assert res.recommended_quote_id == candidates[0].quote_id
    assert res.comparison_scores["best_composite_score"] > 0


@pytest.mark.asyncio
async def test_mock_provider_empty_candidates_raises():
    provider = MockRecommendationProvider()
    with pytest.raises(ValidationError):
        # Pydantic schema enforces min_length=1 on candidates
        RecommendationRequest(
            purchase_id=uuid.uuid4(),
            currency="USD",
            item_description="Fail test",
            category="compute",
            candidates=[],
        )


@pytest.mark.asyncio
async def test_module_adapter_with_sync_function():
    candidates = make_dummy_candidates(2)
    selected_id = candidates[1].quote_id

    # Create dummy dynamic module in sys.modules
    dummy_module_name = "test_teammate_model_sync"
    test_module = types.ModuleType(dummy_module_name)

    def dummy_recommend(req: RecommendationRequest) -> RecommendationResponse:
        return RecommendationResponse(
            recommended_quote_id=selected_id,
            reasoning="Selected candidate 1 by sync ML model.",
            comparison_scores={"model_confidence": 0.94},
            provider_type="module",
            model_version="xgboost-ranker-v1",
        )

    test_module.recommend = dummy_recommend
    sys.modules[dummy_module_name] = test_module

    try:
        adapter = ModuleRecommendationAdapter(module_path=dummy_module_name, timeout=2.0)
        req = make_dummy_request(candidates)
        res = await adapter.recommend(req)

        assert res.recommended_quote_id == selected_id
        assert res.provider_type == "module"
        assert res.model_version == "xgboost-ranker-v1"
        assert res.comparison_scores["model_confidence"] == 0.94
    finally:
        sys.modules.pop(dummy_module_name, None)


@pytest.mark.asyncio
async def test_module_adapter_with_async_function():
    candidates = make_dummy_candidates(2)
    selected_id = candidates[0].quote_id

    dummy_module_name = "test_teammate_model_async"
    test_module = types.ModuleType(dummy_module_name)

    async def dummy_recommend(req: RecommendationRequest) -> dict:
        # Returning dict to verify Pydantic normalization
        return {
            "recommended_quote_id": selected_id,
            "reasoning": "Selected candidate 0 via neural ranker.",
            "comparison_scores": {"neural_loss": 0.05},
            "model_version": "transformer-procure-v2",
        }

    test_module.recommend = dummy_recommend
    sys.modules[dummy_module_name] = test_module

    try:
        adapter = ModuleRecommendationAdapter(module_path=dummy_module_name, timeout=2.0)
        req = make_dummy_request(candidates)
        res = await adapter.recommend(req)

        assert res.recommended_quote_id == selected_id
        assert res.provider_type == "module"
        assert res.model_version == "transformer-procure-v2"
        assert "Selected candidate 0" in res.reasoning
    finally:
        sys.modules.pop(dummy_module_name, None)


@pytest.mark.asyncio
async def test_module_adapter_with_class_export():
    candidates = make_dummy_candidates(2)
    selected_id = candidates[1].quote_id

    dummy_module_name = "test_teammate_model_class"
    test_module = types.ModuleType(dummy_module_name)

    class CustomRecommendationProvider:
        async def recommend(self, req: RecommendationRequest) -> RecommendationResponse:
            return RecommendationResponse(
                recommended_quote_id=selected_id,
                reasoning="Recommended via class-based provider.",
                comparison_scores={"class_score": 1.0},
            )

    test_module.RecommendationProvider = CustomRecommendationProvider
    sys.modules[dummy_module_name] = test_module

    try:
        adapter = ModuleRecommendationAdapter(module_path=dummy_module_name, timeout=2.0)
        req = make_dummy_request(candidates)
        res = await adapter.recommend(req)

        assert res.recommended_quote_id == selected_id
        assert res.provider_type == "module"
    finally:
        sys.modules.pop(dummy_module_name, None)


@pytest.mark.asyncio
async def test_module_adapter_module_not_found_triggers_safe_fallback():
    adapter = ModuleRecommendationAdapter(module_path="non_existent_ml_module_12345", timeout=1.0)
    candidates = make_dummy_candidates(2)
    req = make_dummy_request(candidates)

    res = await adapter.recommend(req)
    assert res.provider_type == "fallback"
    assert "[FALLBACK:" in res.reasoning
    assert res.recommended_quote_id in [c.quote_id for c in candidates]
    assert res.metadata.get("fallback_triggered") is True


@pytest.mark.asyncio
async def test_module_adapter_timeout_triggers_safe_fallback():
    dummy_module_name = "test_teammate_model_slow"
    test_module = types.ModuleType(dummy_module_name)

    async def slow_recommend(req: RecommendationRequest) -> RecommendationResponse:
        await asyncio.sleep(0.5)  # Longer than 0.1s timeout
        return RecommendationResponse(
            recommended_quote_id=req.candidates[0].quote_id,
            reasoning="Too late",
        )

    test_module.recommend = slow_recommend
    sys.modules[dummy_module_name] = test_module

    try:
        adapter = ModuleRecommendationAdapter(module_path=dummy_module_name, timeout=0.1)
        candidates = make_dummy_candidates(2)
        req = make_dummy_request(candidates)

        res = await adapter.recommend(req)
        assert res.provider_type == "fallback"
        assert "timed out" in res.reasoning
        assert res.recommended_quote_id in [c.quote_id for c in candidates]
    finally:
        sys.modules.pop(dummy_module_name, None)


@pytest.mark.asyncio
async def test_module_adapter_exception_triggers_safe_fallback():
    dummy_module_name = "test_teammate_model_crasher"
    test_module = types.ModuleType(dummy_module_name)

    def crashing_recommend(req: RecommendationRequest):
        raise RuntimeError("GPU Out of Memory error during model forward pass")

    test_module.recommend = crashing_recommend
    sys.modules[dummy_module_name] = test_module

    try:
        adapter = ModuleRecommendationAdapter(module_path=dummy_module_name, timeout=1.0)
        candidates = make_dummy_candidates(2)
        req = make_dummy_request(candidates)

        res = await adapter.recommend(req)
        assert res.provider_type == "fallback"
        assert "GPU Out of Memory" in res.reasoning
        assert res.recommended_quote_id in [c.quote_id for c in candidates]
    finally:
        sys.modules.pop(dummy_module_name, None)
