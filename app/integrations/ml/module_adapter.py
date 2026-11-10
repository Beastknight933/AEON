import asyncio
import importlib
from typing import Optional
from app.core.config import settings
from app.core.logging import get_logger
from app.integrations.ml.base import RecommendationProvider
from app.integrations.ml.mock_provider import MockRecommendationProvider
from app.integrations.ml.schemas import RecommendationRequest, RecommendationResponse

logger = get_logger("aeon.ml_adapter")


class ModuleRecommendationAdapter(RecommendationProvider):
    """
    Adapter that dynamically imports and invokes the teammate's eventual ML model module.
    Enforces timeout, input/output contract validation, and graceful fallback to Mock provider.
    """

    def __init__(
        self,
        module_path: Optional[str] = None,
        timeout: Optional[float] = None,
        fallback_provider: Optional[RecommendationProvider] = None,
    ):
        self.module_path = module_path or settings.ML_MODULE_PATH
        self.timeout = timeout or settings.ML_TIMEOUT_SECONDS
        self.fallback_provider = fallback_provider or MockRecommendationProvider()

    @property
    def provider_type(self) -> str:
        return "module"

    async def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        """
        Invoke the teammate's ML model with timeout and strict contract validation.
        Gracefully falls back to the mock provider if the module fails or is unavailable.
        """
        try:
            # 1. Attempt to dynamically load teammate's module
            mod = importlib.import_module(self.module_path)

            # 2. Discover callable: either module-level function or class method
            if hasattr(mod, "recommend"):
                func = getattr(mod, "recommend")
            elif hasattr(mod, "predict"):
                func = getattr(mod, "predict")
            elif hasattr(mod, "get_recommendation"):
                func = getattr(mod, "get_recommendation")
            elif hasattr(mod, "RecommendationProvider"):
                provider_cls = getattr(mod, "RecommendationProvider")
                instance = provider_cls()
                func = getattr(instance, "recommend")
            else:
                raise AttributeError(
                    f"Module '{self.module_path}' does not export 'recommend', 'predict', or 'RecommendationProvider'"
                )

            # 3. Execute with configurable timeout budget
            if asyncio.iscoroutinefunction(func):
                result = await asyncio.wait_for(func(request), timeout=self.timeout)
            else:
                result = await asyncio.wait_for(
                    asyncio.to_thread(func, request),
                    timeout=self.timeout,
                )

            # 4. Enforce Pydantic contract validation
            if isinstance(result, RecommendationResponse):
                validated_res = result
            elif isinstance(result, dict):
                validated_res = RecommendationResponse.model_validate(result)
            else:
                raise ValueError(f"Unexpected return type from model module: {type(result)}")

            # Ensure provider_type is explicitly preserved or set
            if not validated_res.provider_type or validated_res.provider_type == "mock":
                validated_res.provider_type = self.provider_type

            return validated_res

        except (TimeoutError, asyncio.TimeoutError) as e:
            logger.warning(
                f"Teammate ML module '{self.module_path}' timed out after {self.timeout}s: {e}. Executing safe fallback."
            )
            return await self._execute_fallback(request, error_reason=f"Model execution timed out after {self.timeout}s")

        except Exception as e:
            logger.warning(
                f"Teammate ML module '{self.module_path}' invocation failed: {e}. Executing safe fallback recommendation."
            )
            return await self._execute_fallback(request, error_reason=f"Model error: {str(e)}")

    async def _execute_fallback(self, request: RecommendationRequest, error_reason: str) -> RecommendationResponse:
        fallback_res = await self.fallback_provider.recommend(request)
        return RecommendationResponse(
            recommended_quote_id=fallback_res.recommended_quote_id,
            reasoning=f"[FALLBACK: {error_reason}] {fallback_res.reasoning}",
            comparison_scores=fallback_res.comparison_scores,
            provider_type="fallback",
            model_version=fallback_res.model_version,
            metadata={"fallback_triggered": True, "original_error": error_reason},
        )


def get_recommendation_provider() -> RecommendationProvider:
    """
    Factory resolving the active RecommendationProvider based on runtime settings.
    """
    if settings.ML_PROVIDER_TYPE == "module":
        return ModuleRecommendationAdapter()
    return MockRecommendationProvider()
