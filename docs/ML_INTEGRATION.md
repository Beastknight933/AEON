# AEON ML Recommendation Integration Guide

This document defines the interface contract for integrating the ML Recommendation Model developed by the data science/ML teammate.

---

## 1. Core Principle
> **"ML Recommends, but AEON Authorizes."**
> The model selects the most suitable supplier quote based on features like cost, reliability, delivery speed, and historical performance. The backend validates that the recommended quote belongs to the purchase request and verifies it against deterministic policy before spending funds.

---

## 2. Integration Interface Contract

The teammate's Python module can be placed anywhere in the repository or imported as a package.

### Configuration
In `.env`:
```ini
ML_PROVIDER_TYPE=module
ML_MODULE_PATH=app.integrations.ml.teammate_model
ML_TIMEOUT_SECONDS=5.0
```

### Module Requirement
The module specified by `ML_MODULE_PATH` must expose either:
1. A function: `recommend(request: RecommendationRequest) -> RecommendationResponse` (sync or async)
2. Or a class: `RecommendationProvider` with a method `recommend(request: RecommendationRequest) -> RecommendationResponse`

---

## 3. Data Contract Schemas

### Input: `RecommendationRequest`
```python
class QuoteCandidate(BaseModel):
    quote_id: uuid.UUID
    supplier_id: uuid.UUID
    supplier_code: str
    supplier_name: str
    total_amount: Decimal
    currency: str = "USD"
    estimated_delivery_days: int
    reliability_score: Decimal
    attributes: Dict[str, Any]

class RecommendationRequest(BaseModel):
    purchase_id: uuid.UUID
    currency: str = "USD"
    item_description: str
    category: str
    requirements: Dict[str, Any]
    candidates: List[QuoteCandidate]
```

### Output: `RecommendationResponse`
```python
class RecommendationResponse(BaseModel):
    recommended_quote_id: uuid.UUID
    reasoning: str
    comparison_scores: Dict[str, Any]
    provider_type: str = "module"
```

---

## 4. Error Handling & Safe Fallback

If the teammate's model module:
- Raises an uncaught exception,
- Exceeds the configurable timeout (`ML_TIMEOUT_SECONDS`, default 5.0s),
- Returns an invalid quote ID not present in `candidates`, or
- Is not yet implemented / imported,

the backend **gracefully and safely falls back** to the built-in `MockRecommendationProvider` (multi-criteria utility optimizer) with provider_type marked as `"fallback"` and logs the incident. The procurement pipeline will never crash or halt due to an ML model error.
