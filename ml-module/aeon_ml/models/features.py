"""AEON ML Module - Shared Dimension Scoring and Feature Engineering.

Extracts normalized dimension sub-scores, constraint penalties, explainability
drivers, and ML feature matrices without mutating candidate quotes.
"""

from dataclasses import dataclass
from typing import List, Tuple
import numpy as np

from aeon_ml.exceptions import ModelInferenceError
from aeon_ml.schemas import (
    CriteriaWeights,
    ProcurementRequirements,
    ScoreBreakdown,
    SupplierQuote,
)

FEATURE_NAMES: List[str] = [
    "maut_base_norm",
    "price_vs_median",
    "deadline_violation_severity",
    "quality_deficit",
    "reliability_deficit",
    "esg_norm",
    "warranty_norm",
    "experience_norm",
    "budget_headroom",
]


@dataclass(frozen=True)
class QuoteDimensionEvaluation:
    """Intermediate dimension evaluation and engineered feature vector for one quote."""

    quote: SupplierQuote
    sub_scores: ScoreBreakdown
    maut_score: float
    meets_requirements: bool
    key_drivers: List[str]
    features: np.ndarray


def _resolve_weights(requirements: ProcurementRequirements) -> CriteriaWeights:
    """Resolve and normalize criteria weights from requirements."""
    raw = requirements.priority_weights or CriteriaWeights()
    return raw.normalized()


def evaluate_dimensions_and_features(
    quotes: List[SupplierQuote],
    requirements: ProcurementRequirements,
) -> Tuple[List[QuoteDimensionEvaluation], np.ndarray]:
    """Compute interpretable 0-100 sub-scores, MAUT score, and 9-D ML feature matrix."""
    if not quotes:
        return [], np.empty((0, len(FEATURE_NAMES)), dtype=np.float64)

    amounts = np.array([q.amount for q in quotes], dtype=np.float64)
    delivery_days = np.array([q.supplier_attributes.delivery_days for q in quotes], dtype=np.float64)

    min_amount = float(np.min(amounts))
    median_amount = float(np.median(amounts))
    min_delivery = float(np.min(delivery_days))
    weights = _resolve_weights(requirements)

    evaluations: List[QuoteDimensionEvaluation] = []
    feature_rows: List[np.ndarray] = []

    for quote in quotes:
        attrs = quote.supplier_attributes

        # 1. Core dimension sub-scores (0.0 to 100.0)
        price_ratio = min(1.0, max(0.0, min_amount / quote.amount))
        price_score = price_ratio * 100.0

        speed_ratio = min(1.0, max(0.0, min_delivery / attrs.delivery_days))
        speed_score = speed_ratio * 100.0

        quality_score = float(np.clip(attrs.quality_score, 0.0, 100.0))

        base_rel = float(np.clip(attrs.reliability_rating, 0.0, 100.0))
        if attrs.on_time_delivery_rate is not None:
            reliability_score = float(0.6 * base_rel + 0.4 * (attrs.on_time_delivery_rate * 100.0))
        else:
            reliability_score = base_rel

        # 2. Constraint adherence and penalties
        penalty = 0.0
        meets_reqs = True
        key_drivers: List[str] = []

        deadline_slack = 0.0
        deadline_violation = 0.0
        if requirements.max_delivery_days is not None:
            deadline_slack = float(
                np.clip(
                    (requirements.max_delivery_days - attrs.delivery_days) / requirements.max_delivery_days,
                    -1.0,
                    1.0,
                )
            )
            if attrs.delivery_days > requirements.max_delivery_days:
                over_days = attrs.delivery_days - requirements.max_delivery_days
                speed_penalty = min(40.0, over_days * 8.0)
                penalty += speed_penalty
                meets_reqs = False
                deadline_violation = min(1.0, over_days / 5.0)
                key_drivers.append(
                    f"Exceeds max delivery deadline ({attrs.delivery_days}d vs {requirements.max_delivery_days}d req, -{speed_penalty:.0f} pts)"
                )
            else:
                key_drivers.append(f"Meets delivery timeline ({attrs.delivery_days} days)")

        quality_deficit = 0.0
        if requirements.min_quality_score is not None and attrs.quality_score < requirements.min_quality_score:
            qual_diff = requirements.min_quality_score - attrs.quality_score
            qual_penalty = min(30.0, qual_diff * 1.5)
            penalty += qual_penalty
            meets_reqs = False
            quality_deficit = min(1.0, qual_diff / 100.0)
            key_drivers.append(
                f"Below required quality threshold ({attrs.quality_score:.1f} vs {requirements.min_quality_score:.1f} min, -{qual_penalty:.0f} pts)"
            )

        reliability_deficit = 0.0
        if requirements.min_reliability_rating is not None and attrs.reliability_rating < requirements.min_reliability_rating:
            rel_diff = requirements.min_reliability_rating - attrs.reliability_rating
            rel_penalty = min(25.0, rel_diff * 1.2)
            penalty += rel_penalty
            meets_reqs = False
            reliability_deficit = min(1.0, rel_diff / 100.0)
            key_drivers.append(
                f"Below reliability threshold ({attrs.reliability_rating:.1f} vs {requirements.min_reliability_rating:.1f} min, -{rel_penalty:.0f} pts)"
            )

        if quote.amount == min_amount:
            key_drivers.append("Lowest quoted price in candidate pool")
        elif requirements.target_price and quote.amount <= requirements.target_price:
            key_drivers.append(f"Within target budget ({quote.currency} {requirements.target_price:,.2f})")

        # 3. Secondary ML value/risk features
        price_vs_median = float(np.clip((median_amount - quote.amount) / median_amount, -1.0, 1.0)) if median_amount > 0 else 0.0
        esg_norm = (attrs.esg_score / 100.0) if attrs.esg_score is not None else 0.75
        warranty_norm = min(1.0, (attrs.warranty_months or 0) / 36.0)
        experience_norm = min(1.0, float(np.log1p(attrs.past_orders_fulfilled or 0) / np.log1p(100)))
        budget_headroom = (
            float(np.clip((requirements.target_price - quote.amount) / requirements.target_price, -1.0, 1.0))
            if requirements.target_price
            else 0.0
        )

        # 4. Deterministic MAUT utility score (0.0 to 100.0)
        base_score = (
            weights.price_weight * price_score
            + weights.speed_weight * speed_score
            + weights.quality_weight * quality_score
            + weights.reliability_weight * reliability_score
        )
        maut_score = float(np.clip(base_score - penalty, 0.0, 100.0))

        feature_vec = np.array(
            [
                base_score / 100.0,
                price_vs_median,
                deadline_violation,
                quality_deficit,
                reliability_deficit,
                esg_norm,
                warranty_norm,
                experience_norm,
                budget_headroom,
            ],
            dtype=np.float64,
        )

        if not np.all(np.isfinite(feature_vec)):
            raise ModelInferenceError(f"Non-finite feature value computed for quote '{quote.quote_id}'.")

        breakdown = ScoreBreakdown(
            price_score=round(price_score, 2),
            speed_score=round(speed_score, 2),
            quality_score=round(quality_score, 2),
            reliability_score=round(reliability_score, 2),
            penalty_deduction=round(penalty, 2),
        )

        evaluations.append(
            QuoteDimensionEvaluation(
                quote=quote,
                sub_scores=breakdown,
                maut_score=round(maut_score, 2),
                meets_requirements=meets_reqs,
                key_drivers=key_drivers,
                features=feature_vec,
            )
        )
        feature_rows.append(feature_vec)

    return evaluations, np.vstack(feature_rows)


def extract_quote_features(
    quotes: List[SupplierQuote],
    requirements: ProcurementRequirements,
) -> np.ndarray:
    """Convenience helper returning only the (n_quotes, n_features) numpy matrix."""
    _, matrix = evaluate_dimensions_and_features(quotes, requirements)
    return matrix
