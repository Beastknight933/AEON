# AEON ML Recommendation Integration Specification

This document provides the definitive engineering contract for integrating the external Machine Learning (ML) recommendation model into the **AEON Agent Procurement Control Plane**.

---

## 1. Architectural Invariants

AEON enforces the foundational principle:

> **"ML Recommends, but AEON Authorizes."**

1. **Deterministic Financial Control**: The ML model assists in ranking and selecting the optimal supplier quote based on features such as price, reliability, delivery speed, and specifications. However, the model **never** authorizes payments or dictates payable amounts.
2. **Strict Database Truth**: The actual payable amount, currency, and supplier details are **always** loaded directly from the persisted `SupplierQuote` in the database, never from model output.
3. **Candidate Boundary Validation**: The model may only select a quote whose `quote_id` is present in the `candidates` list of the current purchase request. If an unknown or fabricated quote ID is returned, AEON rejects it and automatically triggers a safe fallback.
4. **Hard Policy Precedence**: Even if a quote is strongly recommended by the model, deterministic financial rules (per-transaction caps, daily limits, supplier allow-lists, available budget) take absolute precedence and cannot be bypassed.

---

## 2. Configuration & Activation

To activate your ML model in AEON, set the following environment variables in `.env` (or Render / production configuration):

```ini
# Select the external Python module adapter
ML_PROVIDER_TYPE=module

# Dotted Python import path to your module
ML_MODULE_PATH=app.integrations.ml.teammate_model

# Maximum execution time allowed before triggering safe fallback (in seconds)
ML_TIMEOUT_SECONDS=5.0
```

> **Note**: While your model is in development or not configured, AEON uses `ML_PROVIDER_TYPE=mock`, which runs a deterministic multi-criteria scoring heuristic so the rest of the control plane remains 100% testable and operable.

---

## 3. Function & Module Contract

Your module specified by `ML_MODULE_PATH` can be placed anywhere in Python's `sys.path` (e.g. `app/integrations/ml/teammate_model.py` or an installed package).

The module must implement **at least one** of the following conventions:

### Option A: Module-Level Function (Synchronous or Asynchronous)

```python
from app.integrations.ml.schemas import RecommendationRequest, RecommendationResponse

# Either synchronous:
def recommend(request: RecommendationRequest) -> RecommendationResponse:
    ...

# Or asynchronous:
async def recommend(request: RecommendationRequest) -> RecommendationResponse:
    ...
```

*(Aliases supported: `predict` or `get_recommendation`)*

### Option B: Class-Based Provider

```python
from app.integrations.ml.base import RecommendationProvider
from app.integrations.ml.schemas import RecommendationRequest, RecommendationResponse

class RecommendationProvider:
    def __init__(self):
        # Load your weights, artifacts, or pre-trained models here
        pass

    async def recommend(self, request: RecommendationRequest) -> RecommendationResponse:
        ...
```

---

## 4. Pydantic Schemas

Both input and output schemas are defined in [`app/integrations/ml/schemas.py`](file:///c:/Users/gaumi/Documents/GitHub/AEON/app/integrations/ml/schemas.py).

### Input: `RecommendationRequest`

```python
class QuoteCandidate(BaseModel):
    quote_id: uuid.UUID
        # Primary key of the persisted SupplierQuote. Must be returned in recommended_quote_id.
    supplier_id: uuid.UUID
        # Primary key of the Supplier entity.
    supplier_code: str
        # System identifier (e.g. 'mock_supplier_a', 'aws_marketplace').
    supplier_name: str
        # Display name (e.g. 'MockCloudStore').
    unit_price: Decimal
        # Unit price in USD.
    quantity: int
        # Quantity requested.
    total_amount: Decimal
        # Total cost (unit_price * quantity) in USD.
    currency: str = "USD"
        # Three-letter currency code (USD for MVP).
    estimated_delivery_days: int = 0
        # Delivery latency (0 for instant cloud provisioning).
    reliability_score: Decimal = Decimal("1.00")
        # Historical reliability index between 0.00 and 1.00.
    attributes: Dict[str, Any] = Field(default_factory=dict)
        # Raw specifications, region, SLA, warranty, etc.

class RecommendationRequest(BaseModel):
    purchase_id: uuid.UUID
        # Unique identifier of the purchase request being evaluated.
    currency: str = "USD"
        # Purchase currency.
    item_description: str
        # Natural language description requested by the agent.
    category: str
        # Item classification (e.g. 'compute', 'storage', 'hardware').
    requirements: Dict[str, Any] = Field(default_factory=dict)
        # Agent requirements (region, specs, quantity, etc.).
    candidates: List[QuoteCandidate] = Field(..., min_length=1)
        # List of 1 or more valid candidate quotes collected for this purchase.
```

### Output: `RecommendationResponse`

```python
class RecommendationResponse(BaseModel):
    recommended_quote_id: uuid.UUID
        # The quote_id of the winning candidate. MUST match one of request.candidates.
    reasoning: str
        # Human-readable justification explaining why this quote was selected.
        # This is persisted and visible on the audit trail and dashboard.
    comparison_scores: Dict[str, Any] = Field(default_factory=dict)
        # Structured scores, rankings, or model feature attributions.
    provider_type: str = "module"
        # Identifier tag for the provider.
    model_version: Optional[str] = None
        # Model release/checkpoint identifier (e.g. 'lightgbm-ranker-v1.2').
    metadata: Dict[str, Any] = Field(default_factory=dict)
        # Optional auxiliary metrics or diagnostics.
```

---

## 5. Minimal Working Implementation Template

Save this file as `app/integrations/ml/teammate_model.py`:

```python
import decimal
from app.integrations.ml.schemas import RecommendationRequest, RecommendationResponse

def recommend(request: RecommendationRequest) -> RecommendationResponse:
    candidates = request.candidates
    if not candidates:
        raise ValueError("No candidates provided")

    # Example: score candidates based on price and reliability
    best_candidate = None
    best_score = -1.0
    scores = {}

    for c in candidates:
        # Score calculation (replace with your trained ML model / ranker)
        score = (float(c.reliability_score) * 0.4) + (1.0 / float(c.total_amount) * 100.0 * 0.6)
        scores[str(c.quote_id)] = round(score, 4)

        if score > best_score:
            best_score = score
            best_candidate = c

    assert best_candidate is not None

    return RecommendationResponse(
        recommended_quote_id=best_candidate.quote_id,
        reasoning=(
            f"Selected {best_candidate.supplier_name} based on predictive utility score "
            f"({best_score}) considering price ${best_candidate.total_amount} and "
            f"reliability {best_candidate.reliability_score}."
        ),
        comparison_scores={"scores_by_quote": scores, "top_score": best_score},
        provider_type="module",
        model_version="teammate-ranker-v1.0",
    )
```

---

## 6. Resilience, Timeouts & Error Handling

AEON wraps external model execution inside [`ModuleRecommendationAdapter`](file:///c:/Users/gaumi/Documents/GitHub/AEON/app/integrations/ml/module_adapter.py) with the following safeguards:

1. **Timeout Enforcement**:
   - Model execution is bound by `ML_TIMEOUT_SECONDS` (default: 5.0 seconds).
   - If your model exceeds this budget, AEON cancels the task, logs a warning, and executes the fallback provider without stalling the purchase pipeline.
2. **Exception Containment**:
   - If your model raises an unhandled exception (e.g. `OutOfMemoryError`, missing dependency, unpickling error), AEON catches it, logs the traceback, and invokes the fallback provider.
3. **Invalid Output Protection**:
   - If the model returns a quote ID not present in `request.candidates`, AEON ignores the invalid ID and automatically selects the lowest-priced valid candidate.
4. **Audit Trail**:
   - Fallback activations are recorded with `provider_type="fallback"` and the original error message in the audit log so data science teams can monitor model health.

---

## 7. How to Verify Your Model

Run the AEON ML test suite locally to verify that your model satisfies the contract:

```bash
# Run ML integration unit and flow tests
pytest tests/unit/test_ml_integration.py tests/integration/test_ml_procurement_flow.py -v
```
