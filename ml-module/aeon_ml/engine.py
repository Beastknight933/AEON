"""AEON ML Module - Recommendation Engine & Core Interface.

Fulfills contract:
    recommend(request: RecommendationRequest) -> RecommendationResponse

This module runs strictly in-process within the FastAPI backend.
It does not access databases, does not alter quote amounts, does not make
authorization or payment decisions, and strictly guarantees that the recommended
quote ID exists within the input candidate quotes.
"""

from datetime import datetime, timezone
from typing import Any, Dict, Union

from aeon_ml.backend_bridge import (
    adapt_backend_request,
    format_backend_response,
    is_backend_candidate_request,
)
from aeon_ml.exceptions import (
    AEONMLError,
    EmptyQuotesError,
    ModelInferenceError,
)
from aeon_ml.explainability import generate_recommendation_reasoning
from aeon_ml.models.ranker import HybridMLRanker
from aeon_ml.schemas import (
    RecommendationRequest,
    RecommendationResponse,
)


class QuoteRecommendationEngine:
    """Procurement quote recommendation engine.

    Encapsulates scoring, ranking, explainability, and safety invariant validation.
    """

    def __init__(self, ranker=None) -> None:
        self.ranker = ranker or HybridMLRanker()
        self.version = self.ranker.version

    def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        """Evaluate candidate quotes and return the recommended quote with reasoning and scores.

        Parameters
        ----------
        request : RecommendationRequest
            Input payload containing purchase_id, currency, requirements, and candidate quotes.

        Returns
        -------
        RecommendationResponse
            Structured response containing:
            - recommended_quote_id (strictly from input quotes)
            - reasoning (explainable justification)
            - scores (numeric metrics between 0.0 and 100.0)

        Raises
        ------
        EmptyQuotesError
            If quotes list is empty.
        ModelInferenceError
            If an unexpected failure occurs during evaluation.
        """
        if not request.quotes:
            raise EmptyQuotesError("Cannot generate recommendation without candidate quotes.")

        # Invariant 4 guard: Collect valid quote IDs from request
        valid_quote_ids = {q.quote_id for q in request.quotes}

        try:
            # Evaluate and rank all candidate quotes
            evaluated_metrics = self.ranker.evaluate_quotes(
                quotes=request.quotes,
                requirements=request.requirements,
            )

            if not evaluated_metrics:
                raise ModelInferenceError("Ranker produced an empty evaluation set.")

            # Winning quote is top-ranked (rank 1)
            winner = evaluated_metrics[0]
            recommended_id = winner.quote_id

            # Invariant 4 validation: Model MUST NOT invent quote IDs
            if recommended_id not in valid_quote_ids:
                raise ModelInferenceError(
                    f"Invariant violation: Recommended quote ID '{recommended_id}' "
                    f"was not present in original request quotes: {valid_quote_ids}"
                )

            # Generate explainable decision reasoning
            reasoning = generate_recommendation_reasoning(
                recommended_metric=winner,
                all_metrics=evaluated_metrics,
                requirements=request.requirements,
            )

            # Build validated structured response
            response = RecommendationResponse(
                purchase_id=request.purchase_id,
                recommended_quote_id=recommended_id,
                reasoning=reasoning,
                scores=evaluated_metrics,
                model_version=self.version,
                evaluated_at=datetime.now(timezone.utc),
            )

            return response

        except AEONMLError:
            # Re-raise known domain exceptions cleanly
            raise
        except Exception as exc:
            # Catch unexpected errors and wrap in ModelInferenceError
            raise ModelInferenceError(
                f"Model evaluation failed unexpectedly: {str(exc)}",
                cause=exc,
            ) from exc


# Module-level default singleton engine for zero-configuration in-process import
_default_engine = QuoteRecommendationEngine()


def recommend(request: Union[RecommendationRequest, Any]) -> Union[RecommendationResponse, Dict[str, Any]]:
    """Functional interface matching the AEON integration contract:

    recommend(request: RecommendationRequest) -> RecommendationResponse

    Also transparently adapts AEON backend `QuoteCandidate` payloads
    (`app.integrations.ml.schemas.RecommendationRequest`) when invoked via
    `ModuleRecommendationAdapter`.
    """
    if is_backend_candidate_request(request):
        native_req, candidates_by_id = adapt_backend_request(request)
        native_resp = _default_engine.recommend(native_req)
        return format_backend_response(native_resp, candidates_by_id)

    if isinstance(request, dict):
        request = RecommendationRequest.model_validate(request)

    return _default_engine.recommend(request)

