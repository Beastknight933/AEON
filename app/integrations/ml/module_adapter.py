import asyncio
import importlib
from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.ml.base import BaseRecommendationProvider
from app.integrations.ml.mock_provider import MockRecommendationProvider
from app.integrations.ml.schemas import RecommendationRequest, RecommendationResponse

logger = get_logger("aeon.ml_adapter")


class ModuleRecommendationAdapter(BaseRecommendationProvider):
    """
    Adapter that dynamically imports and invokes the teammate's eventual ML model module.
    Enforces timeout, input/output contract validation, and graceful fallback to Mock provider.
    """

    def __init__(self, module_path: str = settings.ML_MODULE_PATH, timeout: float = settings.ML_TIMEOUT_SECONDS):
        self.module_path = module_path
        self.timeout = timeout
        self.fallback_provider = MockRecommendationProvider()

    @property
    def provider_type(self) -> str:
        return "module"

    async def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        try:
            # Attempt to dynamically load teammate's module
            mod = importlib.import_module(self.module_path)
            # Teammate can expose either a class or a function recommend(request)
            if hasattr(mod, "recommend"):
                func = getattr(mod, "recommend")
            elif hasattr(mod, "RecommendationProvider"):
                provider_cls = getattr(mod, "RecommendationProvider")
                instance = provider_cls()
                func = getattr(instance, "recommend")
            else:
                raise AttributeError(f"Module {self.module_path} does not export 'recommend' or 'RecommendationProvider'")

            # Execute with timeout
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(request), timeout=self.timeout)
            else:
                result = await asyncio.to_thread(func, request)

            # Ensure response matches contract
            if isinstance(result, RecommendationResponse):
                return result
            elif isinstance(result, dict):
                return RecommendationResponse.model_validate(result)
            else:
                raise ValueError(f"Unexpected return type from model module: {type(result)}")

        except Exception as e:
            logger.warning(
                f"Teammate ML module '{self.module_path}' invocation failed: {e}. Executing safe fallback recommendation."
            )
            fallback_res = await self.fallback_provider.recommend(request)
            # Mark fallback in provider_type and reasoning
            return RecommendationResponse(
                recommended_quote_id=fallback_res.recommended_quote_id,
                reasoning=f"[FALLBACK REASONING: Teammate model failed or not loaded: {str(e)}] {fallback_res.reasoning}",
                comparison_scores=fallback_res.comparison_scores,
                provider_type="fallback",
            )


def get_recommendation_provider() -> BaseRecommendationProvider:
    if settings.ML_PROVIDER_TYPE == "module":
        return ModuleRecommendationAdapter()
    return MockRecommendationProvider()
