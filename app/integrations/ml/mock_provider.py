import decimal
from typing import Dict, Any
from app.integrations.ml.base import RecommendationProvider
from app.integrations.ml.schemas import RecommendationRequest, RecommendationResponse


class MockRecommendationProvider(RecommendationProvider):
    """
    Deterministic multi-criteria heuristic recommendation provider used for testing
    and as an automated fallback when an external ML model is unavailable or encounters errors.
    """

    @property
    def provider_type(self) -> str:
        return "mock"

    async def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        candidates = request.candidates
        if not candidates:
            raise ValueError("No candidates provided for recommendation")

        # Find min and max price across candidates to normalize price scoring
        min_price = min(c.total_amount for c in candidates)
        max_price = max(c.total_amount for c in candidates)

        best_candidate = None
        best_composite_score = -1.0
        scores_by_quote: Dict[str, Any] = {}

        for c in candidates:
            # Price score: 1.0 for cheapest, proportional decrease for higher prices
            if max_price == min_price:
                price_score = 1.0
            else:
                price_ratio = float((c.total_amount - min_price) / max_price)
                price_score = max(0.0, 1.0 - price_ratio)

            reliability_score = float(c.reliability_score)
            # Delivery score: 1.0 for instant, penalized 10% per day of delivery delay
            delivery_score = max(0.5, 1.0 - (c.estimated_delivery_days * 0.1))

            # Composite weight: 60% price, 25% reliability, 15% delivery speed
            composite_score = round(
                (price_score * 0.60) + (reliability_score * 0.25) + (delivery_score * 0.15),
                4,
            )

            scores_by_quote[str(c.quote_id)] = {
                "supplier_name": c.supplier_name,
                "total_amount": str(c.total_amount),
                "composite_score": composite_score,
                "price_score": round(price_score, 4),
                "reliability_score": round(reliability_score, 4),
                "delivery_score": round(delivery_score, 4),
            }

            if composite_score > best_composite_score:
                best_composite_score = composite_score
                best_candidate = c

        assert best_candidate is not None
        reasoning = (
            f"Recommended '{best_candidate.supplier_name}' with highest composite utility score "
            f"({best_composite_score}) balancing total cost of ${best_candidate.total_amount} "
            f"against reliability ({best_candidate.reliability_score}) and {best_candidate.estimated_delivery_days} day delivery."
        )

        return RecommendationResponse(
            recommended_quote_id=best_candidate.quote_id,
            reasoning=reasoning,
            comparison_scores={
                "ranking": scores_by_quote,
                "best_composite_score": best_composite_score,
            },
            provider_type=self.provider_type,
            model_version="heuristic-v1.0",
        )
