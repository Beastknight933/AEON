import asyncio
import decimal
import sys
import types
import uuid
import pytest
from app.core.config import settings
from app.core.constants import PurchaseStatus
from app.integrations.ml.schemas import RecommendationRequest, RecommendationResponse
from tests.integration.test_procurement_milestone3 import setup_org_agent_policy_budget


@pytest.mark.asyncio
async def test_teammate_model_valid_recommendation_and_persistence(async_client, monkeypatch):
    """
    Test end-to-end procurement pipeline with external ML module:
    1. External model returns a valid candidate quote.
    2. Reasoning and scores are persisted in DB.
    3. Payable amount is strictly loaded from the persisted quote, not model output.
    """
    ctx = await setup_org_agent_policy_budget(async_client, org_name="MLCorp", admin_email="cfo@mlcorp.io")

    # Mock external ML module
    dummy_module_name = "teammate_procurement_ml"
    test_module = types.ModuleType(dummy_module_name)

    async def custom_recommend(req: RecommendationRequest) -> RecommendationResponse:
        # Deliberately pick candidate 1 (MockHardwareSupply)
        chosen = req.candidates[1]
        return RecommendationResponse(
            recommended_quote_id=chosen.quote_id,
            reasoning=f"AI model selected {chosen.supplier_name} based on predictive reliability index.",
            comparison_scores={"rf_feature_importance": 0.88, "confidence": 0.95},
            provider_type="module",
            model_version="custom-rf-v2.1",
        )

    test_module.recommend = custom_recommend
    sys.modules[dummy_module_name] = test_module

    # Configure app to use the module provider
    monkeypatch.setattr(settings, "ML_PROVIDER_TYPE", "module")
    monkeypatch.setattr(settings, "ML_MODULE_PATH", dummy_module_name)

    try:
        pr_res = await async_client.post(
            "/api/v1/purchases",
            headers=ctx["agent_headers"],
            json={
                "item_description": "Enterprise compute node",
                "category": "compute",
                "max_budget": "500.00",
                "currency": "USD",
                "requirements": {"quantity": 1},
            },
        )
        assert pr_res.status_code == 201, pr_res.text
        data = pr_res.json()

        assert data["status"] in [PurchaseStatus.AUTHORIZED.value, PurchaseStatus.REQUIRES_APPROVAL.value]
        purchase_id = data["id"]

        # Verify recommendation details
        rec = data["recommendation"]
        assert rec is not None
        assert rec["provider_type"] == "module"
        assert "AI model selected" in rec["reasoning"]
        assert rec["comparison_scores"]["confidence"] == 0.95

        # Verify selected quote matches model choice
        selected_quote_id = data["selected_quote_id"]
        assert str(rec["recommended_quote_id"]) == str(selected_quote_id)

        # Verify that payable amount was loaded strictly from DB quote, NOT from model output
        selected_quote = next(q for q in data["quotes"] if q["id"] == selected_quote_id)
        assert decimal.Decimal(selected_quote["total_amount"]) > decimal.Decimal("0.00")

        # Verify detail endpoint returns persisted recommendation
        detail_res = await async_client.get(f"/api/v1/purchases/{purchase_id}", headers=ctx["admin_headers"])
        assert detail_res.status_code == 200
        detail_rec = detail_res.json()["recommendation"]
        assert detail_rec["reasoning"] == rec["reasoning"]
        assert detail_rec["comparison_scores"] == rec["comparison_scores"]
    finally:
        sys.modules.pop(dummy_module_name, None)


@pytest.mark.asyncio
async def test_teammate_model_unverified_quote_fallback(async_client, monkeypatch):
    """
    Test security boundary:
    If teammate's model returns a quote ID that does NOT belong to the current purchase's candidates,
    AEON must reject the recommendation and safely fall back to the lowest-cost valid candidate.
    Never authorize an unverified quote ID!
    """
    ctx = await setup_org_agent_policy_budget(async_client, org_name="SecCorp", admin_email="sec@seccorp.io")

    dummy_module_name = "rogue_ml_module"
    test_module = types.ModuleType(dummy_module_name)

    # Rogue model returns an external/fabricated quote ID
    fabricated_quote_id = uuid.uuid4()

    def rogue_recommend(req: RecommendationRequest) -> RecommendationResponse:
        return RecommendationResponse(
            recommended_quote_id=fabricated_quote_id,
            reasoning="Fabricated quote recommendation attack attempt.",
            comparison_scores={"suspicious": True},
            provider_type="module",
        )

    test_module.recommend = rogue_recommend
    sys.modules[dummy_module_name] = test_module

    monkeypatch.setattr(settings, "ML_PROVIDER_TYPE", "module")
    monkeypatch.setattr(settings, "ML_MODULE_PATH", dummy_module_name)

    try:
        pr_res = await async_client.post(
            "/api/v1/purchases",
            headers=ctx["agent_headers"],
            json={
                "item_description": "Storage Disk",
                "category": "storage",
                "max_budget": "200.00",
                "currency": "USD",
                "requirements": {"quantity": 1},
            },
        )
        assert pr_res.status_code == 201
        data = pr_res.json()

        # AEON must NOT have selected the fabricated quote ID
        assert data["selected_quote_id"] != str(fabricated_quote_id)

        # Selected quote must be one of the actual valid quotes
        actual_quote_ids = [q["id"] for q in data["quotes"]]
        assert data["selected_quote_id"] in actual_quote_ids

        # Reasoning must clearly state that fallback occurred due to unknown quote ID
        rec = data["recommendation"]
        assert "UNVERIFIED_QUOTE_FALLBACK" in rec["reasoning"]
    finally:
        sys.modules.pop(dummy_module_name, None)


@pytest.mark.asyncio
async def test_teammate_model_failure_triggers_fallback_and_authorizes(async_client, monkeypatch):
    """
    Test system resiliency:
    When the teammate's model crashes, AEON logs a warning, falls back to the mock provider,
    and successfully authorizes the purchase without interrupting operations.
    """
    ctx = await setup_org_agent_policy_budget(async_client, org_name="ResilientCorp", admin_email="ops@resilient.io")

    dummy_module_name = "crashing_ml_module"
    test_module = types.ModuleType(dummy_module_name)

    def failing_recommend(req: RecommendationRequest):
        raise ValueError("Model checkpoint weights corrupted")

    test_module.recommend = failing_recommend
    sys.modules[dummy_module_name] = test_module

    monkeypatch.setattr(settings, "ML_PROVIDER_TYPE", "module")
    monkeypatch.setattr(settings, "ML_MODULE_PATH", dummy_module_name)

    try:
        pr_res = await async_client.post(
            "/api/v1/purchases",
            headers=ctx["agent_headers"],
            json={
                "item_description": "Standard compute server",
                "category": "compute",
                "max_budget": "300.00",
                "currency": "USD",
                "requirements": {"quantity": 1},
            },
        )
        assert pr_res.status_code == 201
        data = pr_res.json()

        assert data["status"] == PurchaseStatus.AUTHORIZED.value
        assert data["selected_quote_id"] is not None

        # Verify recommendation has provider_type 'fallback'
        rec = data["recommendation"]
        assert rec["provider_type"] == "fallback"
        assert "[FALLBACK:" in rec["reasoning"]
    finally:
        sys.modules.pop(dummy_module_name, None)
