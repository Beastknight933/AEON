# AEON — Agent Procurement Control Plane

> **"ML Recommends, but AEON Authorizes."**

AEON is an intelligent procurement control plane designed to govern, monitor, and authorize purchases initiated by autonomous AI agents.

As AI agents become increasingly capable of making independent purchasing decisions, organizations need a reliable mechanism to enforce spending policies, validate suppliers, manage budgets, and maintain human oversight.

AEON bridges this gap by introducing a deterministic authorization layer between autonomous agents and financial transactions.

It combines policy-based decision-making, multi-supplier quote evaluation, budget enforcement, human approval workflows, and payment orchestration into a centralized procurement infrastructure.

**Autonomous agents can recommend purchases. AEON controls whether those purchases are authorized.**

---

## Core Capabilities

### 1. Dual Authentication Architecture

Separate authentication mechanisms for human administrators and autonomous agents.

- **Administrator Authentication:** Argon2id password hashing and JWT-based session authentication.
- **Agent Authentication:** Cryptographically secure, one-time API keys.
- **Secure Key Storage:** SHA-256 hashing with constant-time verification.
- **Access Control:** Role-aware API authorization and protected procurement operations.

### 2. Deterministic Procurement Policy Engine

A rule-based authorization engine that evaluates every purchase request against predefined organizational policies.

Enforces:

- Agent activation and authorization status.
- Supplier allow-lists.
- Per-transaction spending limits.
- Daily spending limits.
- Allocated budget constraints.
- Human approval thresholds.
- Currency restrictions.

Hard policy violations cannot be overridden by human approval.

### 3. Atomic Budget Management

AEON incorporates database-level transaction integrity to prevent concurrent spending conflicts.

- PostgreSQL-backed budget management.
- Row-level locking using SQLAlchemy `with_for_update()`.
- Transactional budget reservations.
- Controlled budget settlement and release.
- Protection against duplicate spending and concurrent purchase requests.

### 4. Multi-Supplier Quote Evaluation

A supplier integration layer that enables autonomous procurement workflows to compare competing supplier offers.

- Pluggable supplier registry.
- Mock supplier adapters for cloud and hardware procurement.
- Price comparison.
- Delivery latency evaluation.
- Supplier reliability scoring.
- Structured recommendation output.

### 5. ML-Assisted Procurement Coordination

An extensible ML recommendation layer that evaluates supplier quotes and identifies optimal purchasing options.

The recommendation engine supports:

- Multi-criteria supplier evaluation.
- Composite scoring.
- Structured recommendation responses.
- Explainable purchasing rationales.
- Deterministic fallback mechanisms.

**Important:** ML recommendations are advisory. Final authorization remains under AEON's deterministic policy engine and human approval controls.

### 6. Human-in-the-Loop Authorization

AEON introduces an explicit human approval boundary for procurement operations requiring additional authorization.

- Review recommended suppliers and quotes.
- Inspect policy evaluation results.
- Approve or reject eligible purchase requests.
- Initiate PayPal checkout after approval.
- Maintain an auditable approval history.

### 7. PayPal Orders v2 Integration

Sandbox payment orchestration using the PayPal Orders v2 REST API.

- Order creation with `intent=CAPTURE`.
- Buyer approval and checkout redirection.
- Backend-controlled payment capture.
- PayPal webhook integration.
- Webhook signature verification.
- Idempotency and duplicate-event handling.
- Payment attempt reconciliation.

Payment completion is determined by verified capture evidence rather than buyer approval alone.

### 8. Append-Only Audit Ledger

A centralized audit trail records procurement and authorization activities.

Tracks:

- Agent purchase requests.
- Supplier quote evaluations.
- Policy decisions.
- Human approval actions.
- Budget reservations and settlements.
- PayPal order creation.
- Payment capture events.
- Webhook processing history.

### 9. Procurement Dashboard

A React-based administrative dashboard integrated with the FastAPI backend.

Provides:

- Administrator authentication.
- Agent provisioning and credential management.
- Procurement request submission.
- Supplier recommendation visualization.
- Policy and budget monitoring.
- Transaction ledger.
- Audit event inspection.
- PayPal payment status and reconciliation views.

---

## System Architecture

AEON follows a modular backend architecture with a separately deployable React frontend.

```text
                 AUTONOMOUS AI AGENTS
                          |
                          |
                   Agent API Keys
                          |
                          v
              +-----------------------+
              |     AEON BACKEND      |
              |      FastAPI          |
              +-----------------------+
                          |
             +------------+------------+
             |            |            |
             v            v            v
        Authentication  Procurement  API Layer
             |            |
             |            v
             |      Supplier Registry
             |            |
             |            v
             |      Quote Evaluation
             |            |
             |            v
             |     ML Recommendation
             |            |
             |            v
             |    Policy Engine
             |            |
             |            v
             |    Human Approval
             |            |
             |            v
             |    PayPal Orders v2
             |            |
             |            v
             |    Webhook Verification
             |            |
             |            v
             |    Payment Reconciliation
             |            |
             +------------+
                          |
                          v
                 PostgreSQL Database
                          |
                          v
                  Audit Ledger

                          ^
                          |
                REST API Integration
                          |
                          |
              +-----------------------+
              |    REACT FRONTEND     |
              |     TypeScript        |
              |       Vite            |
              +-----------------------+
                          |
                          v
                ADMINISTRATIVE UI
```

---

## Technology Stack

| Layer | Technologies |
|---|---|
| Backend | Python, FastAPI |
| Frontend | React, TypeScript, Vite |
| Database | PostgreSQL, Supabase |
| ORM | SQLAlchemy 2.x (Async) |
| Migrations | Alembic |
| Validation | Pydantic v2 |
| Authentication | Argon2id, JWT, SHA-256 |
| AI / ML | Python recommendation adapter |
| Payment Gateway | PayPal Orders v2 |
| Styling | Tailwind CSS |
| Deployment | Render, Vercel |
| Testing | Pytest |

---

## Repository Structure

```text
AEON/
│
├── alembic/
│   └── versions/                  # Database migrations
│
├── app/
│   ├── main.py                    # FastAPI application
│   │
│   ├── core/
│   │   ├── config.py              # Environment configuration
│   │   ├── database.py            # Database connections
│   │   ├── security.py            # Authentication and security
│   │   └── logging.py             # Application logging
│   │
│   ├── api/
│   │   └── v1/                    # REST API endpoints
│   │
│   ├── models/                    # SQLAlchemy models
│   ├── schemas/                   # Pydantic schemas
│   ├── services/                  # Business logic
│   ├── engines/                   # Deterministic policy engine
│   ├── integrations/              # PayPal, ML, suppliers
│   ├── repositories/              # Data access layer
│   └── middleware/                # Application middleware
│
├── frontend/
│   ├── src/
│   │   ├── components/            # Dashboard components
│   │   ├── services/              # FastAPI client
│   │   ├── App.tsx                # Main application
│   │   ├── main.tsx               # React entry point
│   │   └── types.ts               # Shared frontend types
│   │
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── tailwind.config.js
│
├── docs/                          # Engineering documentation
├── scripts/                       # Utility scripts
├── tests/                         # Backend tests
│
├── .env.example
├── alembic.ini
├── requirements.txt
├── pytest.ini
├── render.yaml
└── README.md
```

---

## Getting Started

### Prerequisites

Install the following:

- Python 3.11+
- Node.js 20+
- npm
- PostgreSQL or a Supabase PostgreSQL instance
- Git

### 1. Clone the Repository

```bash
git clone https://github.com/Beastknight933/AEON.git

cd AEON
```

### 2. Configure the Backend

Create and activate a Python virtual environment.

**Windows PowerShell:**

```powershell
python -m venv venv

.\venv\Scripts\Activate.ps1
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create your environment file:

```powershell
Copy-Item .env.example .env
```

Configure the required database, authentication, and integration credentials in `.env`.

Never commit actual secrets to GitHub.

### 3. Initialize the Database

Run the Alembic migrations:

```bash
alembic upgrade head
```

### 4. Start the FastAPI Backend

```bash
uvicorn app.main:app --reload --port 8000
```

Backend:

`http://localhost:8000`

Interactive API documentation:

`http://localhost:8000/docs`

Health check:

`http://localhost:8000/health`

### 5. Start the React Frontend

Open a second terminal:

```powershell
cd frontend
```

Install dependencies:

```bash
npm install
```

Create the frontend environment file:

```powershell
Copy-Item .env.example .env
```

Start the development server:

```bash
npm run dev
```

Frontend:

`http://localhost:5173`

The Vite development server proxies API requests to the FastAPI backend.

---

## Procurement Workflow

AEON follows a controlled procurement lifecycle.

```text
AI Agent Initiates Purchase
           |
           v
Authentication & Validation
           |
           v
Supplier Quote Collection
           |
           v
ML-Assisted Quote Evaluation
           |
           v
Deterministic Policy Evaluation
           |
           +----------------------+
           |                      |
           v                      v
      POLICY BLOCKED          POLICY PASSED
           |                      |
           v                      v
      Audit Logging         Human Approval
                                  |
                                  v
                           PayPal Order Creation
                                  |
                                  v
                           Buyer Checkout
                                  |
                                  v
                           PayPal Capture
                                  |
                                  v
                         Webhook Verification
                                  |
                                  v
                       Payment Reconciliation
                                  |
                                  v
                        Budget Settlement
                                  |
                                  v
                        Transaction Ledger
```

---

## Testing

Run the backend test suite:

```bash
pytest -v
```

Run the frontend development build:

```bash
cd frontend

npm run build
```

Payment integration testing should use PayPal Sandbox credentials and test buyer accounts.

Before production deployment, verify:

- Policy enforcement and concurrent budget integrity.
- Duplicate order and capture handling.
- Webhook signature verification.
- Capture-level payment reconciliation.
- Cancellation and reservation release.
- Agent authentication and authorization.
- End-to-end procurement workflows.

---

## Deployment

AEON is designed to support a separately deployed backend and frontend.

| Component | Deployment |
|---|---|
| FastAPI Backend | Render |
| PostgreSQL | Supabase |
| React Frontend | Vercel |
| Payment Gateway | PayPal Sandbox / Live |

Production deployment requires HTTPS, secure environment configuration, database migrations, and correctly configured PayPal return, cancellation, and webhook URLs.

---

## Engineering Documentation

| Documentation | Description |
|---|---|
| [Architecture](docs/ARCHITECTURE.md) | System architecture and sequence diagrams |
| [API Reference](docs/API.md) | REST API specifications |
| [Database](docs/DATABASE.md) | Database entities and relationships |
| [Security](docs/SECURITY.md) | Authentication, authorization and tenancy |
| [ML Integration](docs/ML_INTEGRATION.md) | Recommendation engine contract |
| [PayPal Sandbox](docs/PAYPAL_SANDBOX.md) | Payment integration and testing |
| [Deployment](docs/DEPLOYMENT.md) | Render and Supabase deployment |
| [Demo Runbook](docs/DEMO_RUNBOOK.md) | End-to-end demonstration guide |
| [Hardening Report](docs/ISSUES_AND_HARDENING.md) | Security and reliability improvements |
| [Frontend Integration](docs/FRONTEND_INTEGRATION.md) | React and FastAPI integration |

---

## Project Vision

As autonomous AI agents evolve from information-processing systems into independent economic actors, organizations need infrastructure that can govern their financial decisions.

AEON aims to become that infrastructure.

It introduces a controlled authorization layer between AI-driven purchasing decisions and real-world financial execution, ensuring that autonomy does not come at the expense of accountability.

**AI can recommend. Policies can evaluate. Humans can authorize. AEON governs the transaction.**

---

**AEON — Agent Procurement Control Plane**

*Building the governance infrastructure for autonomous economic agents.*

