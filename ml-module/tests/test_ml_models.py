"""Tests for scikit-learn preference model, hybrid ML ranker, and benchmark evaluation."""

from pathlib import Path
import numpy as np
import pytest

from aeon_ml.evaluation import (
    LowestPriceBaseline,
    evaluate_ranker,
    generate_synthetic_procurement_dataset,
)
from aeon_ml.exceptions import ModelInferenceError
from aeon_ml.models.features import FEATURE_NAMES, extract_quote_features
from aeon_ml.models.preference_model import DEFAULT_ARTIFACT_PATH, SklearnPreferenceModel
from aeon_ml.models.ranker import HybridMLRanker, MultiAttributeRanker
from aeon_ml.schemas import (
    ProcurementRequirements,
    SupplierAttributes,
    SupplierQuote,
)


def test_default_preference_artifact_loads_and_scores():
    model = SklearnPreferenceModel.load_json(DEFAULT_ARTIFACT_PATH)
    assert model.is_fitted

    quotes = [
        SupplierQuote(
            quote_id="Q-1",
            supplier_id="SUP-1",
            amount=1000.0,
            currency="USD",
            supplier_attributes=SupplierAttributes(delivery_days=4, quality_score=92.0, reliability_rating=90.0),
        ),
        SupplierQuote(
            quote_id="Q-2",
            supplier_id="SUP-2",
            amount=1300.0,
            currency="USD",
            supplier_attributes=SupplierAttributes(delivery_days=12, quality_score=75.0, reliability_rating=78.0),
        ),
    ]
    feats = extract_quote_features(quotes, ProcurementRequirements(max_delivery_days=7))
    assert feats.shape == (2, len(FEATURE_NAMES))

    scores = model.predict_scores(feats)
    assert scores.shape == (2,)
    assert np.all((scores >= 0.0) & (scores <= 100.0))
    assert scores[0] > scores[1]


def test_preference_model_fit_and_json_roundtrip(tmp_path: Path):
    rng = np.random.default_rng(123)
    x_train = rng.normal(0.5, 0.2, size=(60, len(FEATURE_NAMES)))
    y_train = (x_train[:, 0] > 0.5).astype(int)

    model = SklearnPreferenceModel(version="test-v1")
    model.fit(x_train, y_train, metadata={"test": True})

    artifact = tmp_path / "model.json"
    model.save_json(artifact)
    loaded = SklearnPreferenceModel.load_json(artifact)

    x_eval = rng.normal(0.5, 0.2, size=(10, len(FEATURE_NAMES)))
    np.testing.assert_allclose(model.predict_scores(x_eval), loaded.predict_scores(x_eval), atol=1e-7)


def test_hybrid_ranker_strict_vs_fallback_on_ml_failure():
    class BrokenPreferenceModel:
        def predict_scores(self, features):
            raise RuntimeError("Corrupted weights")

    quotes = [
        SupplierQuote(
            quote_id="Q-A",
            supplier_id="SUP-A",
            amount=500.0,
            currency="USD",
            supplier_attributes=SupplierAttributes(delivery_days=3, quality_score=90.0, reliability_rating=90.0),
        ),
        SupplierQuote(
            quote_id="Q-B",
            supplier_id="SUP-B",
            amount=700.0,
            currency="USD",
            supplier_attributes=SupplierAttributes(delivery_days=8, quality_score=80.0, reliability_rating=80.0),
        ),
    ]
    reqs = ProcurementRequirements(max_delivery_days=5)

    # Strict mode raises ModelInferenceError
    strict_ranker = HybridMLRanker(preference_model=BrokenPreferenceModel(), fallback_on_ml_error=False)  # type: ignore
    with pytest.raises(ModelInferenceError):
        strict_ranker.evaluate_quotes(quotes, reqs)

    # Fallback mode degrades gracefully to deterministic MAUT scores
    resilient_ranker = HybridMLRanker(preference_model=BrokenPreferenceModel(), fallback_on_ml_error=True)  # type: ignore
    maut_ranker = MultiAttributeRanker()
    res_metrics = resilient_ranker.evaluate_quotes(quotes, reqs)
    maut_metrics = maut_ranker.evaluate_quotes(quotes, reqs)
    assert [m.quote_id for m in res_metrics] == [m.quote_id for m in maut_metrics]
    assert [m.composite_score for m in res_metrics] == [m.composite_score for m in maut_metrics]


def test_evaluation_benchmark_runs_and_beats_naive_baseline():
    eval_data = generate_synthetic_procurement_dataset(n_requests=60, seed=2026)
    naive_report = evaluate_ranker(LowestPriceBaseline(), eval_data, name="LowestPriceBaseline")
    hybrid_report = evaluate_ranker(HybridMLRanker(), eval_data, name="HybridMLRanker")

    assert 0.0 <= naive_report.top1_accuracy <= 1.0
    assert 0.0 <= hybrid_report.top1_accuracy <= 1.0
    assert hybrid_report.top1_accuracy > naive_report.top1_accuracy
    assert hybrid_report.mrr > naive_report.mrr

