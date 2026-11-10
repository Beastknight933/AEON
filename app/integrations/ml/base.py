import abc
from app.integrations.ml.schemas import RecommendationRequest, RecommendationResponse


class BaseRecommendationProvider(abc.ABC):
    @property
    @abc.abstractmethod
    def provider_type(self) -> str:
        pass

    @abc.abstractmethod
    async def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        """
        Evaluate candidate supplier quotes and return recommended quote with scores and rationale.
        """
        pass
