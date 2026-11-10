import abc
from app.integrations.ml.schemas import RecommendationRequest, RecommendationResponse


class RecommendationProvider(abc.ABC):
    """
    Abstract interface for ML-assisted supplier recommendation.
    Both internal mock providers and external teammate ML model adapters
    must implement this interface.
    """

    @property
    @abc.abstractmethod
    def provider_type(self) -> str:
        """
        Provider type identifier, e.g. 'mock', 'module', or 'fallback'.
        """
        pass

    @abc.abstractmethod
    async def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        """
        Evaluate candidate supplier quotes and return a recommended quote with comparison scores and reasoning.
        """
        pass


BaseRecommendationProvider = RecommendationProvider
