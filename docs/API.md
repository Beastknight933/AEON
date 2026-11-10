# AEON REST API Reference (v1)

Base URL: `/api/v1`

All responses and errors follow standardized JSON envelopes.
Interactive OpenAPI docs are available live at `/docs` and `/redoc`.

---

## Centralized Error Response Format

HTTP 4xx / 5xx errors return:
```json
{
  "error": {
    "code": "RESOURCE_NOT_FOUND",
    "message": "Human readable explanation",
    "details": {}
  }
}
```

---

## 1. Authentication & Identity

### `POST /api/v1/auth/register`
Provisions an organization, creates the primary administrator, and returns a signed JWT.

**Request:**
```json
{
  "email": "admin@company.com",
  "password": "Password123!",
  "full_name": "Alice Admin",
  "organization_name": "Autonomous Operations Inc"
}
```
**Response (201 Created):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsIn...",
  "token_type": "bearer",
  "expires_in_minutes": 60
}
```

### `POST /api/v1/auth/login`
Authenticates administrator credentials and returns an access token.

### `GET /api/v1/auth/me`
Retrieves current user identity, organization details, and role (`ADMIN`, `APPROVER`, `MEMBER`).

---

## 2. Agent Management

### `POST /api/v1/agents`
Creates an autonomous agent and generates an individual cryptographically secure API key.
**The raw key is returned ONLY once in this response.**

**Request:**
```json
{
  "name": "CloudComputeAgent",
  "description": "Agent purchasing cloud resources"
}
```
**Response (201 Created):**
```json
{
  "agent": {
    "id": "a1b2c3d4-...",
    "organization_id": "org-...",
    "name": "CloudComputeAgent",
    "is_active": true,
    "created_at": "2026-11-10T12:00:00Z"
  },
  "credentials": {
    "credential_id": "cred-...",
    "agent_id": "a1b2c3d4-...",
    "raw_api_key": "aeon_live_839a8df7...",
    "key_prefix": "aeon_live_839a8d",
    "created_at": "2026-11-10T12:00:00Z"
  }
}
```

### `POST /api/v1/agents/{agent_id}/keys/rotate`
Revokes all active credentials for the agent and issues a new key.

### `DELETE /api/v1/agents/{agent_id}/keys/{credential_id}`
Immediately revokes a specific credential.

---

## 3. Procurement Policies

### `POST /api/v1/policies`
Creates a deterministic procurement policy with version 1 constraints.

**Request:**
```json
{
  "name": "Standard Cloud Procurement",
  "max_amount_per_transaction": "500.00",
  "max_amount_per_day": "2000.00",
  "approval_threshold_amount": "200.00",
  "allowed_suppliers": ["mock_supplier_a", "mock_supplier_b"],
  "allowed_currencies": ["USD"]
}
```

### `POST /api/v1/policies/assignments/{agent_id}`
Assigns a policy to an agent.

---

## 4. Budgets

### `POST /api/v1/budgets`
Allocates an organization-wide or agent-dedicated budget.

**Request:**
```json
{
  "name": "Q4 Compute Pool",
  "allocated_amount": "10000.00",
  "currency": "USD"
}
```

---

## 5. Agent Purchases

### `POST /api/v1/purchases`
**Executed by autonomous agent** using `X-Agent-API-Key: aeon_live_...`.
Triggers quote collection, ML recommendation, deterministic policy evaluation, and budget reservation.

**Request:**
```json
{
  "item_description": "2x Compute Instances",
  "category": "compute",
  "max_budget": "300.00",
  "currency": "USD",
  "requirements": {
    "quantity": 2,
    "region": "us-east-1"
  }
}
```

**Response (201 Created):**
```json
{
  "id": "pr-uuid-...",
  "status": "AUTHORIZED",
  "selected_quote_id": "quote-uuid-...",
  "quotes": [...],
  "recommendation": {
    "provider_type": "mock",
    "recommended_quote_id": "quote-uuid-...",
    "reasoning": "Lowest total price...",
    "comparison_scores": {...}
  }
}
```

---

## 6. Approvals

### `GET /api/v1/approvals`
Lists pending approvals requiring human review.

### `POST /api/v1/approvals/{approval_id}/decide`
Approves or rejects a purchase. Hard policy violations cannot be overridden.

---

## 7. Payments & PayPal

### `POST /api/v1/payments/create-order`
Creates a PayPal Orders v2 with `intent=CAPTURE` for an AUTHORIZED purchase. Returns `approval_url`.

### `POST /api/v1/payments/capture`
Captures an approved PayPal order, settles reserved budget into spent, records ledger transaction, and marks purchase `COMPLETED`.

---

## 8. Dashboard & Audit

### `GET /api/v1/dashboard/overview`
Aggregated counters (total agents, active agents, spent, reserved, available budget, pending approvals) and recent activity logs.

### `GET /api/v1/audit`
Append-only audit trail filtered by `actor_id`, `action`, or `entity_type`.
