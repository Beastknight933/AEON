"""AEON ML Module - Multi-Attribute Utility & Hybrid ML Ranking Models.

Provides:
- MultiAttributeRanker: Deterministic MAUT heuristic baseline (zero artifact dependency).
- HybridMLRanker: Blends interpretable MAUT dimension utility with a trained
  scikit-learn preference scorer (SklearnPreferenceModel), with explicit
  error handling or optional resilient fallback on model failure.
"""

from typing import List, Optional
import numpy as np

from aeon_ml.exceptions import ModelInferenceError
from aeon_ml.models.features import (
    QuoteDimensionEvaluation,
    evaluate_dimensions_and_features,
)
from aeon_ml.models.preference_model import DEFAULT_ARTIFACT_PATH, SklearnPreferenceModel
from aeon_ml.schemas import (
    ProcurementRequirements,
    QuoteEvaluationMetric,
    SupplierQuote,
)


def _rank_and_build_metrics(
    evaluations: List[QuoteDimensionEvaluation],
    composite_scores: List[float],
) -> List[QuoteEvaluationMetric]:
    """Sort evaluated candidates deterministically and construct ranked metrics."""
    records = []
    for item, score in zip(evaluations, composite_scores):
        clipped = round(float(np.clip(score, 0.0, 100.0)), 2)
        records.append(
            {
                "quote": item.quote,
                "composite_score": clipped,
                "sub_scores": item.sub_scores,
                "meets_requirements": item.meets_requirements,
                "key_drivers": list(item.key_drivers),
            }
        )

    sorted_records = sorted(
        records,
        key=lambda r: (
            -r["composite_score"],
            r["quote"].amount,
            r["quote"].supplier_attributes.delivery_days,
            r["quote"].quote_id,
        ),
    )

    return [
        QuoteEvaluationMetric(
            quote_id=rec["quote"].quote_id,
            supplier_id=rec["quote"].supplier_id,
            amount=rec["quote"].amount,
            currency=rec["quote"].currency,
            composite_score=rec["composite_score"],
            rank=idx,
            sub_scores=rec["sub_scores"],
            meets_requirements=rec["meets_requirements"],
            key_drivers=rec["key_drivers"],
        )
        for idx, rec in enumerate(sorted_records, start=1)
    ]


class MultiAttributeRanker:
    """Deterministic Multi-Attribute Utility Theory (MAUT) ranking baseline."""

    def __init__(self, version: str = "aeon-maut-baseline-v1.0.0") -> None:
        self.version = version

    def evaluate_quotes(
        self,
        quotes: List[SupplierQuote],
        requirements: ProcurementRequirements,
    ) -> List[QuoteEvaluationMetric]:
        """Compute deterministic MAUT scores and ranks for candidate quotes."""
        if not quotes:
            return []
        evaluations, _ = evaluate_dimensions_and_features(quotes, requirements)
        scores = [ev.maut_score for ev in evaluations]
        return _rank_and_build_metrics(evaluations, scores)


class HybridMLRanker:
    """Hybrid ML ranker combining MAUT utility with a trained scikit-learn preference model."""

    def __init__(
        self,
        preference_model: Optional[SklearnPreferenceModel] = None,
        ml_weight: float = 0.25,
        fallback_on_ml_error: bool = False,
        version: str = "aeon-ml-hybrid-v1.1.0",
    ) -> None:
        self.version = version
        self.ml_weight = float(np.clip(ml_weight, 0.0, 1.0))
        self.fallback_on_ml_error = fallback_on_ml_error
        self._preference_model = preference_model

    @property
    def preference_model(self) -> SklearnPreferenceModel:
        """Lazily load default trained preference artifact when first accessed."""
        if self._preference_model is None:
            self._preference_model = SklearnPreferenceModel.load_json(DEFAULT_ARTIFACT_PATH)
        return self._preference_model

    def evaluate_quotes(
        self,
        quotes: List[SupplierQuote],
        requirements: ProcurementRequirements,
    ) -> List[QuoteEvaluationMetric]:
        """Score and rank quotes using hybrid MAUT + scikit-learn preference inference."""
        if not quotes:
            return []

        evaluations, feature_matrix = evaluate_dimensions_and_features(quotes, requirements)
        maut_scores = np.array([ev.maut_score for ev in evaluations], dtype=np.float64)

        try:
            ml_scores = self.preference_model.predict_scores(feature_matrix)
            blended = (1.0 - self.ml_weight) * maut_scores + self.ml_weight * ml_scores
            # Ensure non-compliant quotes retain penalty separation
            penalties = np.array([ev.sub_scores.penalty_deduction for ev in evaluations], dtype=np.float64)
            final_scores = np.clip(blended - (0.25 * penalties), 0.0, 100.0).tolist()
        except ModelInferenceError:
            if not self.fallback_on_ml_error:
                raise
            final_scores = maut_scores.tolist()
        except Exception as exc:
            if not self.fallback_on_ml_error:
                raise ModelInferenceError(f"Hybrid ML scoring failed: {exc}", cause=exc) from exc
            final_scores = maut_scores.tolist()

        return _rank_and_build_metrics(evaluations, final_scores)
