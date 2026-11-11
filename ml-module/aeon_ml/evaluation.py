"""AEON ML Module - Offline Evaluation & Synthetic Procurement Benchmark.

Provides:
- Reproducible synthetic procurement dataset generation (disjoint train/eval seeds).
- Standard ranking evaluation metrics: Top-1 Accuracy, Top-2 Hit Rate, MRR, NDCG@3,
  and Constraint Compliance Rate.
- Baseline comparisons (LowestPriceBaseline, MultiAttributeRanker, PureMLRanker, HybridMLRanker).
"""

from dataclasses import dataclass
from typing import Dict, List, Protocol, Tuple
import numpy as np

from aeon_ml.models.features import evaluate_dimensions_and_features, extract_quote_features
from aeon_ml.models.preference_model import DEFAULT_ARTIFACT_PATH, SklearnPreferenceModel
from aeon_ml.models.ranker import HybridMLRanker, MultiAttributeRanker
from aeon_ml.schemas import (
    CriteriaWeights,
    ProcurementRequirements,
    QuoteEvaluationMetric,
    RecommendationRequest,
    SupplierAttributes,
    SupplierQuote,
)


class RankerProtocol(Protocol):
    """Protocol implemented by all rankers evaluated in this benchmark."""

    version: str

    def evaluate_quotes(
        self,
        quotes: List[SupplierQuote],
        requirements: ProcurementRequirements,
    ) -> List[QuoteEvaluationMetric]: ...


@dataclass(frozen=True)
class BenchmarkSample:
    """A single labeled procurement event with the buyer's chosen quote ID."""

    request: RecommendationRequest
    selected_quote_id: str


@dataclass(frozen=True)
class EvaluationReport:
    """Aggregated ranking accuracy and compliance metrics over an evaluation split."""

    model_name: str
    num_requests: int
    top1_accuracy: float
    top2_hit_rate: float
    mrr: float
    ndcg_at_3: float
    constraint_compliance_rate: float

    def to_dict(self) -> Dict[str, object]:
        return {
            "model_name": self.model_name,
            "num_requests": self.num_requests,
            "top1_accuracy": round(self.top1_accuracy, 4),
            "top2_hit_rate": round(self.top2_hit_rate, 4),
            "mrr": round(self.mrr, 4),
            "ndcg_at_3": round(self.ndcg_at_3, 4),
            "constraint_compliance_rate": round(self.constraint_compliance_rate, 4),
        }


class LowestPriceBaseline:
    """Naive baseline that strictly recommends the lowest nominal quote amount."""

    version = "baseline-lowest-price"

    def evaluate_quotes(
        self,
        quotes: List[SupplierQuote],
        requirements: ProcurementRequirements,
    ) -> List[QuoteEvaluationMetric]:
        evaluations, _ = evaluate_dimensions_and_features(quotes, requirements)
        ev_by_id = {ev.quote.quote_id: ev for ev in evaluations}
        sorted_quotes = sorted(quotes, key=lambda q: (q.amount, q.quote_id))
        return [
            QuoteEvaluationMetric(
                quote_id=q.quote_id,
                supplier_id=q.supplier_id,
                amount=q.amount,
                currency=q.currency,
                composite_score=ev_by_id[q.quote_id].sub_scores.price_score,
                rank=idx,
                sub_scores=ev_by_id[q.quote_id].sub_scores,
                meets_requirements=ev_by_id[q.quote_id].meets_requirements,
                key_drivers=[],
            )
            for idx, q in enumerate(sorted_quotes, start=1)
        ]


class PureMLRanker:
    """Pure scikit-learn preference ranker without MAUT blending."""

    def __init__(self, model: SklearnPreferenceModel) -> None:
        self.model = model
        self.version = model.version

    def evaluate_quotes(
        self,
        quotes: List[SupplierQuote],
        requirements: ProcurementRequirements,
    ) -> List[QuoteEvaluationMetric]:
        evaluations, matrix = evaluate_dimensions_and_features(quotes, requirements)
        scores = self.model.predict_scores(matrix)
        paired = sorted(
            zip(evaluations, scores),
            key=lambda pair: (-float(pair[1]), pair[0].quote.amount, pair[0].quote.quote_id),
        )
        return [
            QuoteEvaluationMetric(
                quote_id=ev.quote.quote_id,
                supplier_id=ev.quote.supplier_id,
                amount=ev.quote.amount,
                currency=ev.quote.currency,
                composite_score=round(float(sc), 2),
                rank=idx,
                sub_scores=ev.sub_scores,
                meets_requirements=ev.meets_requirements,
                key_drivers=ev.key_drivers,
            )
            for idx, (ev, sc) in enumerate(paired, start=1)
        ]


def generate_synthetic_procurement_dataset(
    n_requests: int = 500,
    seed: int = 42,
) -> List[BenchmarkSample]:
    """Generate realistic synthetic procurement scenarios with ground-truth selections.

    Models trade-offs across price, lead time, quality, reliability, ESG,
    warranty coverage, fulfillment track record, constraint compliance,
    and realistic stochastic buyer decision noise.
    """
    rng = np.random.default_rng(seed)
    currencies = ["USD", "EUR", "GBP"]
    weight_profiles = [
        CriteriaWeights(price_weight=0.40, speed_weight=0.25, quality_weight=0.20, reliability_weight=0.15),
        CriteriaWeights(price_weight=0.65, speed_weight=0.15, quality_weight=0.10, reliability_weight=0.10),
        CriteriaWeights(price_weight=0.85, speed_weight=0.05, quality_weight=0.05, reliability_weight=0.05),
        CriteriaWeights(price_weight=0.20, speed_weight=0.45, quality_weight=0.20, reliability_weight=0.15),
        CriteriaWeights(price_weight=0.10, speed_weight=0.60, quality_weight=0.15, reliability_weight=0.15),
        CriteriaWeights(price_weight=0.20, speed_weight=0.15, quality_weight=0.40, reliability_weight=0.25),
    ]

    dataset: List[BenchmarkSample] = []

    for req_idx in range(n_requests):
        currency = str(rng.choice(currencies))
        weights = weight_profiles[int(rng.integers(0, len(weight_profiles)))]
        base_budget = float(rng.uniform(2500.0, 50000.0))
        max_days = int(rng.integers(5, 18))
        min_qual = float(rng.choice([70.0, 75.0, 80.0, 85.0]))
        min_rel = float(rng.choice([70.0, 75.0, 80.0, 85.0]))
        n_quotes = int(rng.integers(3, 7))

        quotes: List[SupplierQuote] = []
        latent_utilities: List[float] = []

        for q_idx in range(n_quotes):
            # Realistic price-quality-speed correlation + vendor variation
            tier_quality = float(np.clip(rng.normal(83.0, 10.0), 50.0, 99.0))
            tier_rel = float(np.clip(tier_quality + rng.normal(0.0, 6.0), 50.0, 99.0))
            on_time = float(np.clip((tier_rel / 100.0) + rng.normal(0.0, 0.04), 0.55, 0.99))
            delivery = int(np.clip(round(max_days * rng.uniform(0.45, 1.35)), 1, 30))

            # Faster & higher-quality suppliers tend to quote slightly higher, with noise
            quality_premium = 1.0 + 0.18 * ((tier_quality - 80.0) / 20.0)
            speed_premium = 1.0 + 0.12 * ((max_days - delivery) / max(max_days, 1))
            raw_amount = base_budget * quality_premium * speed_premium * float(rng.uniform(0.84, 1.18))
            amount = round(max(100.0, raw_amount), 2)

            esg = float(np.clip(rng.normal(76.0, 12.0), 35.0, 99.0))
            warranty = int(rng.choice([6, 12, 18, 24, 36]))
            past_orders = int(rng.integers(2, 250))

            quotes.append(
                SupplierQuote(
                    quote_id=f"Q-{req_idx:04d}-{q_idx:02d}",
                    supplier_id=f"SUP-{int(rng.integers(100, 999))}",
                    amount=amount,
                    currency=currency,
                    supplier_attributes=SupplierAttributes(
                        delivery_days=delivery,
                        quality_score=round(tier_quality, 1),
                        reliability_rating=round(tier_rel, 1),
                        on_time_delivery_rate=round(on_time, 3),
                        esg_score=round(esg, 1),
                        warranty_months=warranty,
                        past_orders_fulfilled=past_orders,
                    ),
                )
            )

        has_target_price = bool(rng.random() >= 0.40)
        requirements = ProcurementRequirements(
            max_delivery_days=max_days,
            target_price=round(base_budget, 2) if has_target_price else None,
            min_quality_score=min_qual,
            min_reliability_rating=min_rel,
            priority_weights=weights,
        )

        # Compute latent enterprise buyer choice utility with realistic non-linear risk & secondary preferences
        min_amt = min(q.amount for q in quotes)
        med_amt = float(np.median([q.amount for q in quotes]))
        min_deliv = min(q.supplier_attributes.delivery_days for q in quotes)

        for q in quotes:
            a = q.supplier_attributes
            p_ratio = min_amt / q.amount
            s_ratio = min_deliv / a.delivery_days
            rel_blend = 0.6 * (a.reliability_rating / 100.0) + 0.4 * (a.on_time_delivery_rate or 0.8)

            primary = (
                weights.price_weight * p_ratio
                + weights.speed_weight * s_ratio
                + weights.quality_weight * (a.quality_score / 100.0)
                + weights.reliability_weight * rel_blend
            )
            # Non-linear operational value: savings vs median, budget fit, ESG, warranty, track record
            savings_vs_med = float(np.clip((med_amt - q.amount) / med_amt, -0.5, 0.5))
            budget_fit = (
                (0.08 if q.amount <= base_budget else -0.10 * ((q.amount - base_budget) / base_budget))
                if has_target_price
                else 0.0
            )
            secondary = (
                0.14 * savings_vs_med
                + budget_fit
                + 0.07 * ((a.esg_score or 75.0) / 100.0)
                + 0.06 * min(1.0, (a.warranty_months or 12) / 36.0)
                + 0.05 * min(1.0, float(np.log1p(a.past_orders_fulfilled or 0) / np.log1p(100)))
            )

            # Heavy enterprise compliance penalties
            compliance_penalty = 0.0
            if a.delivery_days > max_days:
                compliance_penalty += 0.35 + 0.08 * (a.delivery_days - max_days)
            if a.quality_score < min_qual:
                compliance_penalty += 0.25 + 0.015 * (min_qual - a.quality_score)
            if a.reliability_rating < min_rel:
                compliance_penalty += 0.20 + 0.012 * (min_rel - a.reliability_rating)

            buyer_noise = float(rng.normal(0.0, 0.035))
            latent_utilities.append(primary + secondary - compliance_penalty + buyer_noise)

        winner_idx = int(np.argmax(latent_utilities))
        dataset.append(
            BenchmarkSample(
                request=RecommendationRequest(
                    purchase_id=f"PO-BENCH-{req_idx:04d}",
                    currency=currency,
                    requirements=requirements,
                    quotes=quotes,
                ),
                selected_quote_id=quotes[winner_idx].quote_id,
            )
        )

    return dataset


def build_training_matrices(dataset: List[BenchmarkSample]) -> Tuple[np.ndarray, np.ndarray]:
    """Convert labeled procurement samples into feature matrix X and binary label vector y."""
    x_blocks: List[np.ndarray] = []
    y_blocks: List[np.ndarray] = []

    for sample in dataset:
        feats = extract_quote_features(sample.request.quotes, sample.request.requirements)
        labels = np.array(
            [1 if q.quote_id == sample.selected_quote_id else 0 for q in sample.request.quotes],
            dtype=np.int64,
        )
        x_blocks.append(feats)
        y_blocks.append(labels)

    return np.vstack(x_blocks), np.concatenate(y_blocks)


def evaluate_ranker(
    ranker: RankerProtocol,
    dataset: List[BenchmarkSample],
    name: str,
) -> EvaluationReport:
    """Evaluate a ranker on a labeled dataset and return ranking accuracy metrics."""
    if not dataset:
        raise ValueError("Evaluation dataset cannot be empty.")

    top1_hits = 0
    top2_hits = 0
    reciprocal_ranks: List[float] = []
    ndcg3_scores: List[float] = []
    compliant_count = 0

    for sample in dataset:
        metrics = ranker.evaluate_quotes(sample.request.quotes, sample.request.requirements)
        rank_by_id = {m.quote_id: m.rank for m in metrics}
        winner_rank = rank_by_id[sample.selected_quote_id]

        if winner_rank == 1:
            top1_hits += 1
        if winner_rank <= 2:
            top2_hits += 1
        reciprocal_ranks.append(1.0 / winner_rank)
        ndcg3_scores.append(1.0 / np.log2(winner_rank + 1.0) if winner_rank <= 3 else 0.0)
        if metrics[0].meets_requirements:
            compliant_count += 1

    n = len(dataset)
    return EvaluationReport(
        model_name=name,
        num_requests=n,
        top1_accuracy=top1_hits / n,
        top2_hit_rate=top2_hits / n,
        mrr=float(np.mean(reciprocal_ranks)),
        ndcg_at_3=float(np.mean(ndcg3_scores)),
        constraint_compliance_rate=compliant_count / n,
    )


def train_and_benchmark(
    train_requests: int = 1200,
    eval_requests: int = 500,
    train_seed: int = 42,
    eval_seed: int = 999,
    save_artifact: bool = True,
) -> Dict[str, EvaluationReport]:
    """Train SklearnPreferenceModel on synthetic training split and benchmark on disjoint test split."""
    train_data = generate_synthetic_procurement_dataset(n_requests=train_requests, seed=train_seed)
    eval_data = generate_synthetic_procurement_dataset(n_requests=eval_requests, seed=eval_seed)

    x_train, y_train = build_training_matrices(train_data)
    pref_model = SklearnPreferenceModel()
    pref_model.fit(
        x_train,
        y_train,
        metadata={
            "dataset_type": "synthetic_procurement_benchmark",
            "train_requests": train_requests,
            "train_quotes": int(x_train.shape[0]),
            "train_seed": train_seed,
        },
    )

    if save_artifact:
        pref_model.save_json(DEFAULT_ARTIFACT_PATH)

    models: List[Tuple[str, RankerProtocol]] = [
        ("LowestPriceBaseline", LowestPriceBaseline()),
        ("MultiAttributeRanker (MAUT)", MultiAttributeRanker()),
        ("PureMLRanker (Sklearn LogReg)", PureMLRanker(pref_model)),
        ("HybridMLRanker (MAUT + Sklearn)", HybridMLRanker(preference_model=pref_model)),
    ]

    return {
        label: evaluate_ranker(ranker, eval_data, name=label)
        for label, ranker in models
    }
