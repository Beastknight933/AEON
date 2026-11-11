"""AEON ML Recommendation Module.

Provides in-process supplier quote comparison and recommendation for AEON FastAPI backend.
Fulfills AEON ML Module Integration Contract:
    recommend(request: RecommendationRequest) -> RecommendationResponse
"""

from aeon_ml.engine import QuoteRecommendationEngine, recommend
from aeon_ml.models import HybridMLRanker, MultiAttributeRanker, SklearnPreferenceModel
from aeon_ml.exceptions import (
    AEONMLError,
    CurrencyMismatchError,
    DuplicateQuoteIdError,
    EmptyQuotesError,
    InvalidQuoteDataError,
    ModelInferenceError,
)
from aeon_ml.schemas import (
    CriteriaWeights,
    ProcurementRequirements,
    QuoteEvaluationMetric,
    RecommendationRequest,
    RecommendationResponse,
    ScoreBreakdown,
    SupplierAttributes,
    SupplierQuote,
)

__version__ = "1.1.0"

__all__ = [
    "recommend",
    "QuoteRecommendationEngine",
    "HybridMLRanker",
    "MultiAttributeRanker",
    "SklearnPreferenceModel",
    "RecommendationRequest",
    "RecommendationResponse",
    "SupplierQuote",
    "SupplierAttributes",
    "ProcurementRequirements",
    "CriteriaWeights",
    "QuoteEvaluationMetric",
    "ScoreBreakdown",
    "AEONMLError",
    "EmptyQuotesError",
    "CurrencyMismatchError",
    "DuplicateQuoteIdError",
    "InvalidQuoteDataError",
    "ModelInferenceError",
]

