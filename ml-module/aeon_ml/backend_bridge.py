"""AEON Backend Integration Bridge.

Adapts AEON backend's `app.integrations.ml.schemas.RecommendationRequest`
(containing `candidates: List[QuoteCandidate]`, Decimal amounts, UUIDs)
into `aeon_ml`'s native `RecommendationRequest` and formats the response to
validate cleanly against `app.integrations.ml.schemas.RecommendationResponse`.
"""

from typing import Any, Dict
import uuid

from aeon_ml.schemas import (
    CriteriaWeights,
    ProcurementRequirements,
    RecommendationRequest,
    RecommendationResponse,
    SupplierAttributes,
    SupplierQuote,
)


def is_backend_candidate_request(request: Any) -> bool:
    """Return True if the request follows AEON backend's QuoteCandidate schema."""
    if isinstance(request, RecommendationRequest):
        return False
    if isinstance(request, dict):
        return "candidates" in request
    return hasattr(request, "candidates")


def _get_attr_or_key(obj: Any, key: str, default: Any = None) -> Any:
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _to_optional_positive_int(val: Any) -> Any:
    if val is None:
        return None
    parsed = int(val)
    return parsed if parsed > 0 else None


def _to_optional_positive_float(val: Any) -> Any:
    if val is None:
        return None
    parsed = float(val)
    return parsed if parsed > 0.0 else None


def adapt_backend_request(request: Any) -> tuple[RecommendationRequest, Dict[str, Any]]:
    """Convert a backend RecommendationRequest (with `candidates`) into `aeon_ml.RecommendationRequest`."""
    purchase_id = str(_get_attr_or_key(request, "purchase_id"))
    currency = str(_get_attr_or_key(request, "currency", "USD")).strip().upper()
    raw_reqs = dict(_get_attr_or_key(request, "requirements", {}) or {})
    raw_candidates = list(_get_attr_or_key(request, "candidates", []) or [])

    weights = raw_reqs.get("priority_weights")
    if isinstance(weights, dict):
        weights = CriteriaWeights(**weights)
    elif not isinstance(weights, CriteriaWeights):
        weights = CriteriaWeights()

    requirements = ProcurementRequirements(
        max_delivery_days=_to_optional_positive_int(
            raw_reqs.get("max_delivery_days") or raw_reqs.get("max_delivery_time")
        ),
        target_price=_to_optional_positive_float(
            raw_reqs.get("target_price") or raw_reqs.get("budget") or raw_reqs.get("max_budget")
        ),
        min_quality_score=raw_reqs.get("min_quality_score"),
        min_reliability_rating=raw_reqs.get("min_reliability_rating"),
        priority_weights=weights,
        notes=raw_reqs.get("notes") or _get_attr_or_key(request, "item_description"),
    )

    quotes = []
    candidates_by_id: Dict[str, Any] = {}

    for cand in raw_candidates:
        quote_id = str(_get_attr_or_key(cand, "quote_id"))
        supplier_id = str(_get_attr_or_key(cand, "supplier_id"))
        amount = float(_get_attr_or_key(cand, "total_amount"))
        cand_currency = str(_get_attr_or_key(cand, "currency", currency)).strip().upper()
        est_days = _get_attr_or_key(cand, "estimated_delivery_days", 1)
        delivery_days = max(1, int(est_days if est_days is not None else 1))

        rel_raw = float(_get_attr_or_key(cand, "reliability_score", 0.8))
        reliability_rating = rel_raw * 100.0 if 0.0 <= rel_raw <= 1.0 else max(0.0, min(100.0, rel_raw))

        attrs = dict(_get_attr_or_key(cand, "attributes", {}) or {})
        qual_raw = float(attrs.get("quality_score", 80.0))
        quality_score = qual_raw * 100.0 if 0.0 < qual_raw <= 1.0 else max(0.0, min(100.0, qual_raw))

        on_time = attrs.get("on_time_delivery_rate")
        if on_time is not None:
            on_time = float(on_time)
            if on_time > 1.0:
                on_time = min(1.0, on_time / 100.0)

        esg = attrs.get("esg_score")
        if esg is not None:
            esg = float(esg)
            if 0.0 < esg <= 1.0:
                esg *= 100.0

        quotes.append(
            SupplierQuote(
                quote_id=quote_id,
                supplier_id=supplier_id,
                amount=amount,
                currency=cand_currency,
                supplier_attributes=SupplierAttributes(
                    delivery_days=delivery_days,
                    quality_score=quality_score,
                    reliability_rating=reliability_rating,
                    on_time_delivery_rate=on_time,
                    esg_score=esg,
                    warranty_months=int(attrs.get("warranty_months", 12)),
                    past_orders_fulfilled=int(attrs.get("past_orders_fulfilled", 0)),
                ),
            )
        )
        candidates_by_id[quote_id] = cand

    return (
        RecommendationRequest(
            purchase_id=purchase_id,
            currency=currency,
            requirements=requirements,
            quotes=quotes,
        ),
        candidates_by_id,
    )


def format_backend_response(
    response: RecommendationResponse,
    candidates_by_id: Dict[str, Any],
) -> Dict[str, Any]:
    """Convert `aeon_ml.RecommendationResponse` into AEON backend `RecommendationResponse` dict."""
    try:
        rec_uuid: Any = uuid.UUID(response.recommended_quote_id)
    except ValueError:
        rec_uuid = response.recommended_quote_id

    ranking: Dict[str, Any] = {}
    for metric in response.scores:
        cand = candidates_by_id[metric.quote_id]
        ranking[metric.quote_id] = {
            "supplier_name": _get_attr_or_key(cand, "supplier_name", metric.supplier_id),
            "supplier_code": _get_attr_or_key(cand, "supplier_code", metric.supplier_id),
            "total_amount": str(_get_attr_or_key(cand, "total_amount", metric.amount)),
            "composite_score": round(metric.composite_score / 100.0, 4),
            "composite_score_100": metric.composite_score,
            "rank": metric.rank,
            "meets_requirements": metric.meets_requirements,
            "sub_scores": metric.sub_scores.model_dump(),
            "key_drivers": metric.key_drivers,
        }

    best_score_100 = response.scores[0].composite_score
    return {
        "recommended_quote_id": rec_uuid,
        "reasoning": response.reasoning,
        "comparison_scores": {
            "ranking": ranking,
            "best_composite_score": round(best_score_100 / 100.0, 4),
            "best_composite_score_100": best_score_100,
            "score_scale": "0.0-1.0 (composite_score) / 0.0-100.0 (composite_score_100)",
        },
        "provider_type": "module",
        "model_version": response.model_version,
        "metadata": {
            "purchase_id": response.purchase_id,
            "evaluated_at": response.evaluated_at.isoformat(),
            "candidate_count": len(response.scores),
        },
    }
