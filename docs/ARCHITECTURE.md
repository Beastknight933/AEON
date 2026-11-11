# AEON Backend Architecture & System Design

## 1. Executive Overview

**AEON** is an Agent Procurement Control Plane governing autonomous transactions initiated by AI agents.

### Central Architectural Tenet
> **"ML Recommends, but AEON Authorizes."**
> Machine learning models assist in comparing suppliers and recommending optimal quotes, but no ML model output may override deterministic financial, organizational, or security policies.

---

## 2. High-Level Modular Monolith Architecture

AEON is constructed as a high-performance modular monolith using **FastAPI**, **SQLAlchemy 2.x async**, and **Pydantic v2**.

```mermaid
flowchart TD
    Agent[Autonomous AI Agent] -->|X-Agent-API-Key| Gateway[FastAPI API Gateway]
    Admin[Dashboard Admin] -->|Bearer JWT| Gateway
    Vercel[Vercel Frontend] -->|REST API| Gateway

    subgraph AEON Modular Monolith
        Gateway --> Auth[Identity & Security Engine]
        Gateway --> Proc[Procurement Pipeline Service]
        Gateway --> Policy[Deterministic Policy Engine]
        Gateway --> Budget[Budget & Reservation Engine]
        Gateway --> Payment[PayPal Orders v2 Service]
        Gateway --> Audit[Append-Only Audit Ledger]

        Proc --> ML[ML Recommendation Adapter]
        Proc --> Supp[Supplier Registry & Adapters]
    end

    ML --> AeonML[aeon_ml Hybrid ML Ranker]
    Supp --> MockA[MockCloudStore]
    Supp --> MockB[MockHardwareSupply]
    Payment --> PayPal[PayPal Sandbox Orders v2]
    AEON Modular Monolith --> DB[(Supabase PostgreSQL)]
```

---

## 3. End-to-End Procurement Flow

```mermaid
sequenceDiagram
    autonumber
    actor Agent as Autonomous Agent
    participant AEON as AEON Control Plane
    participant Suppliers as Supplier Adapters
    participant ML as ML Recommendation Adapter
    participant Policy as Deterministic Policy Engine
    participant Budget as Budget Integrity Engine
    actor Human as Human Approver
    participant PayPal as PayPal Sandbox API

    Agent->>AEON: POST /api/v1/purchases (Requirements, Max Budget)
    AEON->>AEON: Authenticate Agent (constant-time API key hash check)
    AEON->>Suppliers: Concurrent quote request (MockCloudStore, MockHardwareSupply)
    Suppliers-->>AEON: Normalized quotes returned
    AEON->>AEON: Persist quotes to database
    AEON->>ML: recommend(candidates, requirements)
    ML-->>AEON: Recommended quote ID + rationale
    AEON->>AEON: Validate recommended quote ID against persisted quotes
    AEON->>Policy: Evaluate deterministic rules (Status, Limits, Allowed Suppliers, Budget)
    alt Hard Policy Violation
        AEON-->>Agent: Purchase BLOCKED (Reason codes returned)
    else Policy Pass
        AEON->>Budget: Atomic reserve_funds_atomic (Row-level lock)
        alt Amount > Approval Threshold
            AEON->>AEON: Status = REQUIRES_APPROVAL (Approval record created)
            Human->>AEON: POST /api/v1/approvals/{id}/decide (APPROVE)
            AEON->>AEON: Status = AUTHORIZED
        else Amount <= Approval Threshold
            AEON->>AEON: Status = AUTHORIZED
        end
        AEON->>PayPal: POST /v2/checkout/orders (intent=CAPTURE)
        PayPal-->>AEON: Order ID & Approval URL
        AEON-->>Agent: Return Authorization & Order Link
    end
```

---

## 4. Lifecycle State Machines

To prevent ambiguous states, **Purchase**, **Payment**, and **Fulfillment** lifecycles are decoupled:

### Purchase Lifecycle
`REQUESTED` $\rightarrow$ `QUOTING` $\rightarrow$ `RECOMMENDED` $\rightarrow$ (`BLOCKED` | `REQUIRES_APPROVAL` | `AUTHORIZED`) $\rightarrow$ (`CANCELLED` | `COMPLETED`)

### Payment Lifecycle
`NOT_STARTED` $\rightarrow$ `ORDER_CREATED` $\rightarrow$ `BUYER_APPROVAL_PENDING` $\rightarrow$ `CAPTURE_PENDING` $\rightarrow$ `COMPLETED` | `FAILED` | `REFUNDED`

### Fulfillment Lifecycle
`NOT_STARTED` $\rightarrow$ `PENDING` $\rightarrow$ `DELIVERED` | `FAILED`

---

## 5. Budget Integrity & Concurrency

- **Formula**: `Available Budget = Allocated Amount - Reserved Amount - Spent Amount`
- **Atomic Reservations**: Row-level locking with `SELECT ... FOR UPDATE` prevents concurrent race conditions and double-spending across autonomous agents.
- **Settle vs. Release**:
  - Payment capture success: Settle reservation (`reserved -= amount`, `spent += amount`).
  - Payment failure or human rejection: Release reservation (`reserved -= amount`).
  - Refund: Record reversal transaction and refund budget (`spent -= amount`).
