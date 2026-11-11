"""AEON ML Module - Pydantic Data Schemas.

Strict, immutable schemas defining the contract between AEON FastAPI backend
and the ML quote recommendation engine.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from aeon_ml.exceptions import (
    CurrencyMismatchError,
    DuplicateQuoteIdError,
    EmptyQuotesError,
    InvalidQuoteDataError,
)


class SupplierAttributes(BaseModel):
    """Supplier performance, delivery, and compliance attributes.

    All supplier metrics are immutable during recommendation processing.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    delivery_days: int = Field(
        ...,
        ge=1,
        description="Quoted delivery timeline in calendar days.",
    )
    quality_score: float = Field(
        default=80.0,
        ge=0.0,
        le=100.0,
        allow_inf_nan=False,
        description="Historical or benchmark quality score (scale: 0.0 to 100.0).",
    )
    reliability_rating: float = Field(
        default=80.0,
        ge=0.0,
        le=100.0,
        allow_inf_nan=False,
        description="Historical supplier reliability rating (scale: 0.0 to 100.0).",
    )
    on_time_delivery_rate: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=1.0,
        allow_inf_nan=False,
        description="Historical ratio of on-time deliveries (scale: 0.0 to 1.0).",
    )
    esg_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        allow_inf_nan=False,
        description="Environmental, Social, and Governance compliance score (scale: 0.0 to 100.0).",
    )
    warranty_months: Optional[int] = Field(
        default=12,
        ge=0,
        description="Warranty period provided in months.",
    )
    past_orders_fulfilled: Optional[int] = Field(
        default=0,
        ge=0,
        description="Total number of successfully fulfilled purchase orders.",
    )


class SupplierQuote(BaseModel):
    """A single quote submitted by a supplier for a purchase event.

    Strictly immutable (frozen=True) to guarantee that the ML module cannot
    alter supplier quote amounts, IDs, currencies, or attributes.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    quote_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the supplier's quote.",
    )
    supplier_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the supplier.",
    )
    amount: float = Field(
        ...,
        gt=0.0,
        allow_inf_nan=False,
        description="Total monetary amount of the quote. Must be strictly positive.",
    )
    currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="ISO 4217 three-letter currency code (e.g. USD, EUR, GBP).",
    )
    supplier_attributes: SupplierAttributes = Field(
        ...,
        description="Detailed performance and operational metrics of the supplier.",
    )

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.strip().upper()
        return v


class CriteriaWeights(BaseModel):
    """Weights used in Multi-Attribute Utility calculation.

    If weights do not sum to 1.0, they are automatically normalized.
    """

    model_config = ConfigDict(frozen=True)

    price_weight: float = Field(default=0.40, ge=0.0, le=1.0, allow_inf_nan=False)
    speed_weight: float = Field(default=0.25, ge=0.0, le=1.0, allow_inf_nan=False)
    quality_weight: float = Field(default=0.20, ge=0.0, le=1.0, allow_inf_nan=False)
    reliability_weight: float = Field(default=0.15, ge=0.0, le=1.0, allow_inf_nan=False)

    def normalized(self) -> "CriteriaWeights":
        """Return normalized weights that sum to 1.0."""
        total = self.price_weight + self.speed_weight + self.quality_weight + self.reliability_weight
        if total <= 0:
            return CriteriaWeights(price_weight=0.4, speed_weight=0.25, quality_weight=0.2, reliability_weight=0.15)
        return CriteriaWeights(
            price_weight=round(self.price_weight / total, 4),
            speed_weight=round(self.speed_weight / total, 4),
            quality_weight=round(self.quality_weight / total, 4),
            reliability_weight=round(self.reliability_weight / total, 4),
        )


class ProcurementRequirements(BaseModel):
    """Procurement constraints, preferences, and benchmark requirements."""

    model_config = ConfigDict(extra="allow")

    max_delivery_days: Optional[int] = Field(
        default=None,
        gt=0,
        description="Maximum acceptable delivery time in calendar days.",
    )
    target_price: Optional[float] = Field(
        default=None,
        gt=0.0,
        allow_inf_nan=False,
        description="Reference target budget (non-enforcing; used for reference scoring only).",
    )
    min_quality_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        allow_inf_nan=False,
        description="Minimum acceptable supplier quality score.",
    )
    min_reliability_rating: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        allow_inf_nan=False,
        description="Minimum acceptable supplier reliability rating.",
    )
    priority_weights: Optional[CriteriaWeights] = Field(
        default_factory=CriteriaWeights,
        description="Custom weighting across price, speed, quality, and reliability.",
    )
    notes: Optional[str] = Field(
        default=None,
        description="Optional human-readable notes or procurement context.",
    )


class RecommendationRequest(BaseModel):
    """Input payload for quote recommendation.

    Matches contract:
    - purchase_id
    - currency
    - requirements
    - a list of available quotes (each containing quote_id, supplier_id, amount, currency, supplier_attributes)
    """

    purchase_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier of the purchase requisition.",
    )
    currency: str = Field(
        ...,
        min_length=3,
        max_length=3,
        description="Three-letter ISO currency code expected for all quotes in this purchase.",
    )
    requirements: ProcurementRequirements = Field(
        default_factory=ProcurementRequirements,
        description="Procurement requirements and preferences.",
    )
    quotes: List[SupplierQuote] = Field(
        ...,
        description="List of available quotes to compare.",
    )

    @field_validator("currency", mode="before")
    @classmethod
    def normalize_currency(cls, v: Any) -> str:
        if isinstance(v, str):
            return v.strip().upper()
        return v

    @model_validator(mode="after")
    def validate_request_invariants(self) -> "RecommendationRequest":
        # 1. Non-empty quote list
        if not self.quotes:
            raise EmptyQuotesError("Quote list cannot be empty. At least one quote is required.")

        # 2. Currency consistency check
        req_curr = self.currency
        invalid_quotes = [
            {"quote_id": q.quote_id, "currency": q.currency}
            for q in self.quotes
            if q.currency != req_curr
        ]
        if invalid_quotes:
            raise CurrencyMismatchError(req_curr, invalid_quotes)

        # 3. Unique quote IDs
        quote_ids = [q.quote_id for q in self.quotes]
        if len(quote_ids) != len(set(quote_ids)):
            duplicates = [qid for qid in set(quote_ids) if quote_ids.count(qid) > 1]
            raise DuplicateQuoteIdError(duplicates)

        # 4. Strict positive amount check
        for q in self.quotes:
            if q.amount <= 0:
                raise InvalidQuoteDataError(
                    f"Quote '{q.quote_id}' has non-positive amount {q.amount}.",
                    details={"quote_id": q.quote_id, "amount": q.amount},
                )

        return self


class ScoreBreakdown(BaseModel):
    """Component sub-scores evaluated on a documented 0.0 to 100.0 numeric range."""

    price_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Price competitiveness score (0.0 to 100.0, higher is better value).",
    )
    speed_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Delivery speed score (0.0 to 100.0, faster delivery yields higher score).",
    )
    quality_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Quality metric score (0.0 to 100.0).",
    )
    reliability_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Supplier reliability score (0.0 to 100.0).",
    )
    penalty_deduction: float = Field(
        default=0.0,
        ge=0.0,
        le=100.0,
        description="Penalty points deducted due to unmet delivery or quality requirements.",
    )


class QuoteEvaluationMetric(BaseModel):
    """Evaluation metrics and rank for a single candidate quote."""

    quote_id: str = Field(..., description="Unique quote identifier.")
    supplier_id: str = Field(..., description="Supplier identifier.")
    amount: float = Field(..., description="Original quote amount (unmodified).")
    currency: str = Field(..., description="Quote currency.")
    composite_score: float = Field(
        ...,
        ge=0.0,
        le=100.0,
        description="Overall multi-criteria composite score (range: 0.0 to 100.0).",
    )
    rank: int = Field(
        ...,
        ge=1,
        description="1-based ranking among all evaluated quotes (1 = best).",
    )
    sub_scores: ScoreBreakdown = Field(
        ...,
        description="Detailed sub-score breakdown across individual dimensions.",
    )
    meets_requirements: bool = Field(
        ...,
        description="True if all stated procurement requirements are satisfied.",
    )
    key_drivers: List[str] = Field(
        default_factory=list,
        description="Key positive or negative factors contributing to this quote's score.",
    )


class RecommendationResponse(BaseModel):
    """Output contract from the ML recommendation module.

    Contains:
    - recommended_quote_id
    - reasoning
    - scores / comparison metrics (strictly numeric, range 0.0 to 100.0)

    Includes runtime invariants guaranteeing that recommended_quote_id matches
    an actual quote from the request.
    """

    purchase_id: str = Field(
        ...,
        description="Purchase requisition identifier matching the input request.",
    )
    recommended_quote_id: str = Field(
        ...,
        description="Quote ID selected as the best overall recommendation.",
    )
    reasoning: str = Field(
        ...,
        description="Explainable human-readable justification for the recommendation.",
    )
    scores: List[QuoteEvaluationMetric] = Field(
        ...,
        description="List of all evaluated candidate quotes with numeric scores and ranks.",
    )
    model_version: str = Field(
        default="aeon-ml-ranker-v1.0.0",
        description="Identifier of the ML model/engine version used.",
    )
    evaluated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="UTC timestamp of the recommendation computation.",
    )

    @model_validator(mode="after")
    def validate_response_invariants(self) -> "RecommendationResponse":
        evaluated_ids = [s.quote_id for s in self.scores]
        if self.recommended_quote_id not in evaluated_ids:
            raise ValueError(
                f"Invariant violation: recommended_quote_id '{self.recommended_quote_id}' "
                f"is not among evaluated quote IDs: {evaluated_ids}"
            )
        return self
