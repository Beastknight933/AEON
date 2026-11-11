"""AEON ML Module - Explainability and Reasoning Generation.

Generates human-readable, auditable decision justifications for procurement teams
explaining why a specific supplier quote was recommended over available alternatives.
"""

from typing import List
from aeon_ml.schemas import ProcurementRequirements, QuoteEvaluationMetric


def generate_recommendation_reasoning(
    recommended_metric: QuoteEvaluationMetric,
    all_metrics: List[QuoteEvaluationMetric],
    requirements: ProcurementRequirements,
) -> str:
    """Generate a structured, transparent narrative explaining the recommendation.

    Highlights:
    1. Winning score and primary value drivers (cost, speed, quality, reliability).
    2. Comparison against the runner-up quote, detailing exact trade-offs.
    3. Requirement compliance status.
    """
    total_quotes = len(all_metrics)
    winning_id = recommended_metric.quote_id
    winning_supplier = recommended_metric.supplier_id
    winning_score = recommended_metric.composite_score
    winning_amount = recommended_metric.amount
    winning_currency = recommended_metric.currency

    # Sort metrics by rank
    ranked_metrics = sorted(all_metrics, key=lambda m: m.rank)

    # Base opening
    lines = [
        f"Quote '{winning_id}' from supplier '{winning_supplier}' is recommended with the highest "
        f"composite score of {winning_score:.2f}/100 among {total_quotes} candidate quote(s)."
    ]

    # Winning drivers
    drivers = []
    sub = recommended_metric.sub_scores
    if sub.price_score >= 85.0:
        drivers.append(f"strong price competitiveness (score: {sub.price_score:.1f}/100)")
    elif sub.price_score >= 70.0:
        drivers.append(f"competitive pricing (score: {sub.price_score:.1f}/100)")

    if sub.speed_score >= 85.0:
        drivers.append(f"rapid delivery timeline (score: {sub.speed_score:.1f}/100)")

    if sub.quality_score >= 85.0:
        drivers.append(f"high quality assurance rating ({sub.quality_score:.1f}/100)")

    if sub.reliability_score >= 85.0:
        drivers.append(f"proven supplier reliability ({sub.reliability_score:.1f}/100)")

    if drivers:
        lines.append(f"Key performance drivers: {', '.join(drivers)}.")

    # Requirements check
    if recommended_metric.meets_requirements:
        lines.append("Adherence: Meets all specified procurement constraints and delivery requirements.")
    else:
        lines.append("Adherence Note: Best available fit, though some target preferences were compromised.")

    # Runner-up comparison (if multiple quotes exist)
    if len(ranked_metrics) > 1:
        runner_up = ranked_metrics[1]
        score_diff = winning_score - runner_up.composite_score
        price_diff = runner_up.amount - winning_amount

        if price_diff > 0:
            comp_text = (
                f"Runner-up comparison: Outperforms quote '{runner_up.quote_id}' "
                f"(supplier '{runner_up.supplier_id}', score: {runner_up.composite_score:.2f}/100) "
                f"by +{score_diff:.2f} points, delivering a cost savings of "
                f"{winning_currency} {abs(price_diff):,.2f}."
            )
        elif price_diff < 0:
            comp_text = (
                f"Runner-up comparison: Quote '{runner_up.quote_id}' offers a lower nominal price "
                f"({winning_currency} {runner_up.amount:,.2f}), but '{winning_id}' is recommended "
                f"due to superior operational reliability and delivery metrics (+{score_diff:.2f} overall score)."
            )
        else:
            comp_text = (
                f"Runner-up comparison: Tied in pricing with quote '{runner_up.quote_id}', "
                f"but achieves higher utility (+{score_diff:.2f} points) in quality and speed."
            )
        lines.append(comp_text)

    # Disqualified or heavily penalized quotes note
    penalized = [m for m in all_metrics if m.sub_scores.penalty_deduction > 0 and m.quote_id != winning_id]
    if penalized:
        penalized_info = [f"'{m.quote_id}' (-{m.sub_scores.penalty_deduction:.0f} pts)" for m in penalized]
        lines.append(f"Risk adjustment: Penalties applied to non-compliant quotes: {', '.join(penalized_info)}.")

    return " ".join(lines)

