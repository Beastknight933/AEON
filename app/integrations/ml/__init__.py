from app.integrations.ml.base import RecommendationProvider, BaseRecommendationProvider
from app.integrations.ml.mock_provider import MockRecommendationProvider
from app.integrations.ml.module_adapter import ModuleRecommendationAdapter, get_recommendation_provider
from app.integrations.ml.schemas import QuoteCandidate, RecommendationRequest, RecommendationResponse

__all__ = [
    "RecommendationProvider",
    "BaseRecommendationProvider",
    "MockRecommendationProvider",
    "ModuleRecommendationAdapter",
    "get_recommendation_provider",
    "QuoteCandidate",
    "RecommendationRequest",
    "RecommendationResponse",
]
