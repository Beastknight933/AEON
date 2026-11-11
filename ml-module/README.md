# AEON — ML Module Integration Contract & Implementation

## 1. Overview & System Context

This repository provides the production-grade Python ML recommendation module for the **AEON** procurement platform's six-day MVP.

### Purpose and Responsibilities
- **Core Role**: Compares available supplier quotes for a given procurement request and recommends the most suitable quote based on multi-attribute utility optimization.
- **Architectural Boundary**: Runs strictly **in-process** within the AEON FastAPI backend service.
- **Explicit Non-Responsibilities**:
  - The model **does not** access databases or external network services.
  - The model **does not** modify supplier quote amounts or vendor data.
  - The model **does not** authorize purchases, enforce budgets, determine payment amounts, or override organizational policies.
  - The model **never invents** quote IDs.

---

## 2. Required Interface

The package exposes both a direct functional interface and an object-oriented engine:

```python
from aeon_ml import recommend, RecommendationRequest, RecommendationResponse

response: RecommendationResponse = recommend(request: RecommendationRequest)
```

Or via class instance:
```python
from aeon_ml import QuoteRecommendationEngine

engine = QuoteRecommendationEngine()
response = engine.recommend(request)
```

---

## 3. Data Schemas

All schemas are implemented using Pydantic v2 with strict validation and immutability guarantees.

### 3.1 Input Schema (`RecommendationRequest`)

```python
class RecommendationRequest(BaseModel):
    purchase_id: str                      # Unique requisition identifier
    currency: str                         # 3-letter ISO 4217 currency code (e.g., 'USD', 'EUR')
    requirements: ProcurementRequirements # Constraints and criteria weighting
    quotes: List[SupplierQuote]           # Non-empty list of candidate quotes
```

#### Nested Input Models:
- **`SupplierQuote`** (`frozen=True`):
  - `quote_id: str` — Unique quote identifier.
  - `supplier_id: str` — Unique supplier identifier.
  - `amount: float` — Quoted price (must be strictly $> 0.0$).
  - `currency: str` — Must match `request.currency`.
  - `supplier_attributes: SupplierAttributes` — Operational & performance metrics.

- **`SupplierAttributes`**:
  - `delivery_days: int` — Quoted turnaround time in days ($\ge 1$).
  - `quality_score: float` — Benchmark quality score (scale: $0.0$ to $100.0$, default: $80.0$).
  - `reliability_rating: float` — Historical reliability rating (scale: $0.0$ to $100.0$, default: $80.0$).
  - `on_time_delivery_rate: Optional[float]` — Historical SLA ratio ($0.0$ to $1.0$).
  - `esg_score: Optional[float]` — Environmental, Social, and Governance score ($0.0$ to $100.0$).
  - `warranty_months: Optional[int]` — Warranty duration in months (default: $12$).
  - `past_orders_fulfilled: Optional[int]` — Total successfully fulfilled orders.

- **`ProcurementRequirements`**:
  - `max_delivery_days: Optional[int]` — Maximum acceptable lead time.
  - `target_price: Optional[float]` — Budget benchmark (reference only; non-enforcing).
  - `min_quality_score: Optional[float]` — Minimum quality threshold.
  - `min_reliability_rating: Optional[float]` — Minimum reliability threshold.
  - `priority_weights: Optional[CriteriaWeights]` — Custom criteria weights (price, speed, quality, reliability).

---

### 3.2 Output Schema (`RecommendationResponse`)

```python
class RecommendationResponse(BaseModel):
    purchase_id: str                      # Matches input purchase_id
    recommended_quote_id: str             # Selected quote ID (guaranteed to be from input)
    reasoning: str                        # Human-readable decision narrative
    scores: List[QuoteEvaluationMetric]   # Ranked evaluation metrics for all candidates
    model_version: str                    # ML model version (e.g., 'aeon-ml-ranker-v1.0.0')
    evaluated_at: datetime                # UTC timestamp of recommendation
```

#### Nested Output Models:
- **`QuoteEvaluationMetric`**:
  - `quote_id: str` — Candidate quote ID.
  - `supplier_id: str` — Supplier ID.
  - `amount: float` — Original quote amount (unmodified).
  - `currency: str` — Currency.
  - `composite_score: float` — **Documented numeric range: $0.0$ to $100.0$** (higher is better).
  - `rank: int` — 1-based rank ($1$ = winning recommendation).
  - `sub_scores: ScoreBreakdown` — Component scores ($0.0$ to $100.0$ each for price, speed, quality, reliability, minus penalties).
  - `meets_requirements: bool` — True if candidate satisfies all stated constraints.
  - `key_drivers: List[str]` — Explainability drivers and penalty notes.

---

## 4. Scoring Algorithm, ML Layer & Benchmark

The engine uses **`HybridMLRanker`** (`aeon-ml-hybrid-v1.1.0`), combining interpretable **Multi-Attribute Utility Theory (MAUT)** with a trainable **scikit-learn `LogisticRegression` preference scorer** (`SklearnPreferenceModel`):

1. **Price Utility ($S_{\text{price}} \in [0.0, 100.0]$)**:
   $$S_{\text{price}} = \min\left(100.0, \frac{\min(\text{amounts})}{\text{amount}} \times 100.0\right)$$
   The lowest price receives $100.0$; higher prices receive smooth proportional scores without artificial cut-offs.

2. **Lead Time Utility ($S_{\text{speed}} \in [0.0, 100.0]$)**:
   $$S_{\text{speed}} = \min\left(100.0, \frac{\min(\text{delivery\_days})}{\text{delivery\_days}} \times 100.0\right)$$

3. **Quality & Reliability ($S_{\text{quality}}, S_{\text{reliability}} \in [0.0, 100.0]$)**:
   Combines quality ratings, supplier reliability scores, and historical on-time fulfillment rates.

4. **Constraint Penalties**:
   - Quotes exceeding `max_delivery_days` receive a penalty of $8.0$ points per day late (capped at $40.0$).
   - Quotes falling below `min_quality_score` receive $1.5$ penalty points per deficit point (capped at $30.0$).
   - Quotes falling below `min_reliability_rating` receive $1.2$ penalty points per deficit point (capped at $25.0$).

5. **Trained Preference Model & Hybrid Composite Score ($S_{\text{composite}} \in [0.0, 100.0]$)**:
   Extracts 9 engineered features (`maut_base_norm`, `price_vs_median`, `deadline_violation_severity`, `quality_deficit`, `reliability_deficit`, `esg_norm`, `warranty_norm`, `experience_norm`, `budget_headroom`), scores win probability via `SklearnPreferenceModel` (`StandardScaler` + `LogisticRegression`, stored safely as JSON weights in `aeon_ml/models/artifacts/preference_model.json`), and blends $(1 - w_{\text{ml}}) S_{\text{MAUT}} + w_{\text{ml}} S_{\text{ML}}$ minus constraint penalties.
   Ties are broken deterministically by: (1) lowest price, (2) shortest delivery days, (3) lexicographical ID.

### Synthetic Benchmark Results (Disjoint 500-Requisition Held-Out Split)
*(Note: Evaluated via `python scripts/train_and_evaluate.py` on synthetic procurement data — train seed `42` on 1,200 requisitions, test seed `999` on 500 unseen requisitions. Real production accuracy should be measured once historical AEON buyer selections are logged.)*

| Model | Top-1 Accuracy | Top-2 Hit Rate | MRR | NDCG@3 | Compliant |
|---|---|---|---|---|---|
| `LowestPriceBaseline` | 16.60% | 39.40% | 0.4394 | 0.4329 | 17.00% |
| `MultiAttributeRanker (MAUT)` | 75.40% | 93.40% | 0.8653 | 0.8966 | 69.60% |
| `PureMLRanker (Sklearn LogReg)` | 76.40% | 94.80% | 0.8728 | 0.9031 | 71.00% |
| `HybridMLRanker (MAUT + Sklearn)` | **78.40%** | **95.00%** | **0.8832** | **0.9107** | **71.60%** |

---

## 5. Adherence to 9 Integration Requirements

| # | Requirement | Implementation Guarantee |
|---|---|---|
| **1** | **No database access** | Pure functional module. No database drivers, ORM sessions, or network sockets are imported or used. |
| **2** | **No quote amount modification** | `SupplierQuote` is a Pydantic `frozen=True` model. Quote amounts are immutable and verified in unit tests. |
| **3** | **No authorization or payment decisions** | The output contains only `recommended_quote_id`, `reasoning`, and `scores`. No authorization status, payment triggers, or policy overrides exist. |
| **4** | **Do not invent quote IDs** | The engine asserts that `recommended_quote_id` belongs strictly to `[q.quote_id for q in request.quotes]`, validated both at runtime and in Pydantic validators. |
| **5** | **Structured results, not unvalidated text** | Returns strongly typed `RecommendationResponse` instances with JSON Schema serialization support. |
| **6** | **Documented Python dependencies** | Defined in `requirements.txt` and `pyproject.toml` (`pydantic`, `numpy`, `scikit-learn`). |
| **7** | **Minimal runnable example** | Executable script provided in `examples/minimal_runnable.py`. |
| **8** | **Comprehensive test cases** | 29 tests in `tests/` covering end-to-end recommendation, backend bridge compatibility, ML scoring/fallback, edge cases, error handling, and all safety invariants. |
| **9** | **Error handling for model failures** | Dedicated exception hierarchy (`EmptyQuotesError`, `CurrencyMismatchError`, `DuplicateQuoteIdError`, `ModelInferenceError`) plus optional fallback mode. |

---

## 6. Directory Layout

```
ml-module/
├── aeon_ml/                        # Core ML package
│   ├── __init__.py                 # Public interface and exports
│   ├── schemas.py                  # Pydantic v2 input and output models
│   ├── backend_bridge.py           # Adapter for AEON backend QuoteCandidate payloads
│   ├── engine.py                   # QuoteRecommendationEngine & recommend() function
│   ├── evaluation.py               # Synthetic benchmark & ranking metrics
│   ├── exceptions.py               # Domain exceptions
│   ├── explainability.py           # Narrative and reasoning generator
│   └── models/
│       ├── __init__.py
│       ├── features.py             # Feature engineering & sub-score extraction
│       ├── preference_model.py     # Trainable scikit-learn LogisticRegression scorer
│       ├── ranker.py               # MultiAttributeRanker & HybridMLRanker
│       └── artifacts/
│           └── preference_model.json # Fitted scaler & classifier parameters
├── examples/
│   ├── minimal_runnable.py         # Standalone runnable demonstration
│   └── fastapi_adapter.py          # FastAPI backend service adapter
├── scripts/
│   └── train_and_evaluate.py       # Train preference model & print benchmark metrics
├── tests/
│   ├── __init__.py
│   ├── test_recommendation.py      # End-to-end recommendation tests
│   ├── test_backend_bridge.py      # AEON ModuleRecommendationAdapter compatibility tests
│   ├── test_ml_models.py           # ML model, fallback & evaluation tests
│   ├── test_safety_invariants.py   # Invariant enforcement tests
│   ├── test_error_handling.py      # Error handling and validation tests
│   ├── test_schemas.py             # Schema tests
│   └── test_fastapi_adapter.py     # FastAPI integration tests
├── .gitignore                      # Excludes caches, virtualenvs, and build artifacts
├── requirements.txt                # Production dependencies
├── requirements-dev.txt            # Development/testing dependencies
├── pyproject.toml                  # Build configuration and pytest settings
└── README.md                       # Integration contract documentation
```

---

## 7. Installation & Quickstart

### 7.1 Install Dependencies

```bash
pip install -r requirements.txt
```

For development and running tests:
```bash
pip install -r requirements-dev.txt
```

### 7.2 Run the Minimal Example

```bash
python examples/minimal_runnable.py
```

### 7.3 Run Tests

```bash
python -m pytest -v
```

---

## 8. Backend Integration Guide (FastAPI)

The AEON backend team can integrate `aeon_ml` into their existing FastAPI application in three lines of code:

```python
from fastapi import FastAPI, HTTPException, status
from aeon_ml import recommend, RecommendationRequest, RecommendationResponse, AEONMLError

app = FastAPI()

@app.post("/api/v1/procurement/recommendations", response_model=RecommendationResponse)
async def create_recommendation(request: RecommendationRequest) -> RecommendationResponse:
    try:
        # In-process execution: Zero DB calls inside the ML module
        return recommend(request)
    except AEONMLError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={"error": exc.__class__.__name__, "message": exc.message, "details": exc.details},
        )
```

### AEON `ModuleRecommendationAdapter` Integration (`app/integrations/ml/`)

From the root of the AEON repository, install the module in editable mode and point `.env` to `aeon_ml`:

```bash
pip install -e ./ml-module
```

Set in AEON backend environment:
```env
ML_PROVIDER_TYPE=module
ML_MODULE_PATH=aeon_ml
```

`aeon_ml.recommend` automatically detects `QuoteCandidate` payloads from `app.integrations.ml.schemas.RecommendationRequest` and returns a validated `RecommendationResponse` dictionary with `provider_type="module"`.

A complete, runnable standalone FastAPI adapter server is provided in [`examples/fastapi_adapter.py`](examples/fastapi_adapter.py).

