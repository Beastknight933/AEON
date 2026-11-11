# AEON — Agent Procurement Control Plane

> **"ML Recommends, but AEON Authorizes."**

AEON is an enterprise-grade backend control plane designed to govern, budget, and authorize purchases initiated by autonomous AI agents.

---

## Key Features

- **Dual Independent Authentication**: Argon2id & JWT for dashboard administrators; cryptographically secure, one-time raw API keys with SHA-256 hash storage and constant-time verification for AI agents.
- **Deterministic Policy Engine**: Enforces strict agent active state, supplier allow-lists, per-transaction spending limits, daily rolling spend limits, budget caps, and human approval thresholds. Hard violations cannot be overridden by human approvers.
- **Atomic Budget Integrity**: Row-level locking (`with_for_update()`) prevents concurrent race conditions and double-spending across autonomous agents.
- **Multi-Supplier Quote Collection**: Pluggable supplier registry with mock cloud and hardware supplier adapters for the MVP.
- **ML Recommendation Integration**: In-process hybrid ML ranking engine (`aeon_ml`) combining scikit-learn preference learning with multi-attribute scoring heuristics and automated explainability justifications, backed by an immutable database contract and safe fallback.
- **PayPal Orders v2 Payments**: Backend order creation (`intent=CAPTURE`), buyer approval redirect URLs, backend capture, and verified idempotent webhook processing.
- **Append-Only Audit Ledger**: Application-level immutable audit trail tracking all agent actions, policy evaluations, and payment events.
- **Production-Ready**: FastAPI, SQLAlchemy 2.x async, Supabase PostgreSQL, Alembic migrations, pre-configured for Render deployment and Vercel frontend integration.

---

## Repository Structure

```
AEON/
├── alembic/                      # Alembic async migration scripts (6 revisions)
├── app/
│   ├── main.py                   # FastAPI application factory & router mounting
│   ├── core/                     # Config, database, security, errors, logging
│   ├── api/v1/                   # Thin REST API endpoints
│   ├── models/                   # SQLAlchemy 2.x models (19 entities)
│   ├── schemas/                  # Pydantic v2 validation contracts
│   ├── services/                 # Business logic & transaction orchestration
│   ├── engines/                  # Deterministic Policy Engine
│   ├── integrations/             # PayPal, ML adapter, and Supplier integrations
│   ├── repositories/             # Data access layer
│   └── middleware/               # Correlation ID & Centralized Error Handling
├── docs/                         # Comprehensive engineering documentation
├── ml-module/                    # Autonomous ML supplier quote recommendation engine
│   ├── aeon_ml/                  # Core package (ranker, models, bridge, explainability)
│   ├── tests/                    # ML module test suite (30 tests)
│   └── pyproject.toml            # Packaging & setuptools build metadata
├── scripts/                      # Database seeding and development utilities
├── tests/                        # Control plane unit, integration, and E2E test suites (80 tests)
├── requirements.txt              # Backend production dependencies
├── render.yaml                   # Render deployment configuration
└── .env.example                  # Environment variable reference
```

---

## Quickstart (Local Development)

### 1. Install Dependencies
```bash
pip install -r requirements.txt
pip install -e ml-module
```

### 2. Configure Environment
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
*(Optionally set `ML_PROVIDER_TYPE=module` to activate the in-process ML ranker).*

### 3. Run Database Migrations
```bash
alembic upgrade head
```

### 4. (Optional) Seed Initial Data
```bash
python scripts/seed.py
```

### 5. Start the Application
```bash
uvicorn app.main:app --reload --port 8000
```
Visit the interactive OpenAPI documentation at `http://localhost:8000/docs`.

---

## Running Tests

Run the complete control plane and ML test suites:
```bash
# Run all 110 tests
pytest tests ml-module/tests -v

# Or run backend control plane tests only (80 tests)
pytest tests -v

# Or run ML module tests only (30 tests)
pytest ml-module/tests -v
```

---

## Documentation Links

- [Architecture & Sequence Diagrams](docs/ARCHITECTURE.md)
- [REST API Reference](docs/API.md)
- [Database Schema & 19 Entities](docs/DATABASE.md)
- [Security Model & Tenancy](docs/SECURITY.md)
- [ML Recommendation Contract](docs/ML_INTEGRATION.md)
- [PayPal Sandbox Integration](docs/PAYPAL_SANDBOX.md)
- [Render & Supabase Deployment](docs/DEPLOYMENT.md)
- [Master Demo Runbook](docs/DEMO_RUNBOOK.md)
- [Hardening & Issues Report](docs/ISSUES_AND_HARDENING.md)
