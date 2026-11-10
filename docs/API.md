# AEON REST API Reference (v1)

Base URL: `/api/v1`  
Interactive OpenAPI documentation is available live at `/docs` (Swagger UI) and `/redoc` (ReDoc).

---

## 1. Architecture & Design Standards

AEON is an **Agent Procurement Control Plane** governing purchases initiated by autonomous AI agents. The REST API is designed for clean integration with external web frontends (e.g. React/TypeScript) and autonomous agents.

### Key Standards:
1. **Authentication**:
   - **Dashboard Administrators / Approvers**: Short-lived signed JWT bearer tokens (`Authorization: Bearer <token>`).
   - **Autonomous Agents**: Cryptographic API keys (`X-Agent-API-Key: aeon_live_<secret>`). Raw keys are returned only once upon creation.
2. **Organization Isolation**: Every resource belongs to an organization. Cross-organization access is rejected with `404 Not Found` to prevent resource enumeration.
3. **Deterministic Financial Decoupling**: Purchases, payments, and fulfillments have independent lifecycles (`PurchaseStatus`, `PaymentStatus`, `FulfillmentStatus`). Browser redirects are never accepted as proof of payment.
4. **Standard Pagination Envelope**:
   ```json
   {
     "items": [...],
     "total": 100,
     "page": 1,
     "page_size": 20,
     "total_pages": 5
   }
   ```
5. **Standard Error Envelope**:
   ```json
   {
     "error": {
       "code": "RESOURCE_NOT_FOUND",
       "message": "Resource with identifier '...' not found",
       "details": {}
     }
   }
   ```

---

## 2. API Endpoints Catalog

| Method | Path | Description | Auth Required |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | Register organization & admin account | None |
| `POST` | `/api/v1/auth/login` | Login and acquire JWT access token | None |
| `GET` | `/api/v1/auth/me` | Current authenticated user profile | Bearer JWT |
| `POST` | `/api/v1/agents` | Register autonomous agent & issue API key | Bearer JWT (Admin) |
| `GET` | `/api/v1/agents` | List agents for organization | Bearer JWT |
| `GET` | `/api/v1/agents/{agent_id}` | Retrieve specific agent details | Bearer JWT |
| `POST` | `/api/v1/agents/{agent_id}/keys/rotate` | Rotate agent API credentials | Bearer JWT (Admin) |
| `DELETE` | `/api/v1/agents/{agent_id}/keys/{cred_id}` | Revoke specific agent credential | Bearer JWT (Admin) |
| `POST` | `/api/v1/policies` | Create deterministic spend policy | Bearer JWT (Admin) |
| `GET` | `/api/v1/policies` | List policies for organization | Bearer JWT |
| `GET` | `/api/v1/policies/{policy_id}` | Get policy details and published versions | Bearer JWT |
| `POST` | `/api/v1/policies/assignments/{agent_id}` | Assign policy to an agent | Bearer JWT (Admin) |
| `POST` | `/api/v1/budgets` | Allocate organization or agent budget | Bearer JWT (Admin) |
| `GET` | `/api/v1/budgets` | List budgets and active balances | Bearer JWT |
| `POST` | `/api/v1/purchases` | Submit autonomous purchase request | Agent API Key |
| `GET` | `/api/v1/purchases` | List purchase requests | Bearer JWT |
| `GET` | `/api/v1/purchases/{purchase_id}` | Retrieve purchase details and quotes | Bearer JWT |
| `GET` | `/api/v1/approvals` | List pending human approval requests | Bearer JWT |
| `POST` | `/api/v1/approvals/{approval_id}/decide` | Approve or reject a purchase request | Bearer JWT (Approver/Admin) |
| `POST` | `/api/v1/payments/create-order` | Create PayPal Orders v2 with CAPTURE intent | Bearer JWT (Admin/Approver) |
| `POST` | `/api/v1/payments/capture` | Capture PayPal order & settle budget | Bearer JWT (Admin/Approver) |
| `GET` | `/api/v1/payments/{order_id}` | Query payment attempt status | Bearer JWT |
| `POST` | `/api/v1/payments/{order_id}/reconcile` | Reconcile order against PayPal authoritative API | Bearer JWT (Admin/Approver) |
| `POST` | `/api/v1/payments/reconcile` | Batch reconcile all in-flight orders | Bearer JWT (Admin/Approver) |
| `POST` | `/api/v1/payments/webhook` | Asynchronous PayPal webhook receiver | Public (HMAC Verified) |
| `GET` | `/api/v1/dashboard/overview` | KPI counters and recent activity stream | Bearer JWT |
| `GET` | `/api/v1/dashboard/stats` | Real-time budget, agent, and purchase counters | Bearer JWT |
| `GET` | `/api/v1/dashboard/spending` | Spending breakdown by category, supplier, agent | Bearer JWT |
| `GET` | `/api/v1/dashboard/agents` | Performance & spend summaries for every agent | Bearer JWT |
| `GET` | `/api/v1/transactions` | Paginated financial ledger transactions | Bearer JWT |
| `GET` | `/api/v1/transactions/{id}` | Detailed transaction with purchase context | Bearer JWT |
| `GET` | `/api/v1/transactions/{id}/timeline` | Audit-backed chronological event timeline | Bearer JWT |
| `GET` | `/api/v1/transactions/{id}/receipt` | Verifiable digital receipt for accounting | Bearer JWT |
| `GET` | `/api/v1/transactions/reconcile` | Financial reconciliation totals & counts | Bearer JWT |
| `GET` | `/api/v1/audit` | Paginated immutable audit trail | Bearer JWT |

---

## 3. End-to-End Workflow Examples

### Workflow 1: Admin Registration & Authentication

#### 1. Register Organization & Admin
```bash
curl -X POST https://aeon.app/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "sarah.admin@acmecorp.com",
    "password": "SecurePassword2026!",
    "full_name": "Sarah Connor",
    "organization_name": "Acme Autonomous Corp"
  }'
```
**Response (201 Created):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in_minutes": 60
}
```

#### 2. Inspect Profile
```bash
curl -X GET https://aeon.app/api/v1/auth/me \
  -H "Authorization: Bearer <TOKEN>"
```
**Response (200 OK):**
```json
{
  "user": {
    "id": "e932b2e8-466d-4958-867c-9b7e9bf1f221",
    "email": "sarah.admin@acmecorp.com",
    "full_name": "Sarah Connor",
    "is_active": true
  },
  "organization": {
    "id": "37f632eb-bfe9-4114-834f-37023b67947e",
    "name": "Acme Autonomous Corp",
    "slug": "acme-autonomous-corp"
  },
  "role": "ADMIN"
}
```

---

### Workflow 2: Agent Provisioning & Key Generation

```bash
curl -X POST https://aeon.app/api/v1/agents \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "CloudOps-AutoProcure-Bot",
    "description": "Agent handling cloud compute provisioning"
  }'
```
**Response (201 Created):**
```json
{
  "agent": {
    "id": "c85c2c77-49db-4876-b6b6-a21239c05421",
    "organization_id": "37f632eb-bfe9-4114-834f-37023b67947e",
    "name": "CloudOps-AutoProcure-Bot",
    "description": "Agent handling cloud compute provisioning",
    "is_active": true,
    "created_at": "2026-11-10T22:00:00Z"
  },
  "credentials": {
    "credential_id": "b38d3889-13e6-42d8-9fa8-1f19f18a2211",
    "agent_id": "c85c2c77-49db-4876-b6b6-a21239c05421",
    "raw_api_key": "aeon_live_839a8df749c92138adfe91039",
    "key_prefix": "aeon_live_839a8d",
    "created_at": "2026-11-10T22:00:00Z"
  }
}
```
> [!IMPORTANT]
> The `raw_api_key` is returned **only once** upon creation. Only its cryptographic hash is stored on the server.

---

### Workflow 3: Procurement Policy Definition & Assignment

#### 1. Define Policy
```bash
curl -X POST https://aeon.app/api/v1/policies \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Standard Cloud Procurement Policy",
    "description": "Enforces limits and supplier allow-lists for compute purchases",
    "max_amount_per_transaction": "500.00",
    "max_amount_per_day": "2000.00",
    "approval_threshold_amount": "250.00",
    "allowed_suppliers": ["mock_supplier_a", "mock_supplier_b"],
    "allowed_currencies": ["USD"]
  }'
```

#### 2. Assign Policy to Agent
```bash
curl -X POST https://aeon.app/api/v1/policies/assignments/c85c2c77-49db-4876-b6b6-a21239c05421 \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "policy_id": "993a401b-c743-47cb-9da8-39210bb87102"
  }'
```

---

### Workflow 4: Budget Allocation

```bash
curl -X POST https://aeon.app/api/v1/budgets \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Q4 Cloud Infrastructure Budget",
    "allocated_amount": "5000.00",
    "currency": "USD"
  }'
```
**Response (201 Created):**
```json
{
  "id": "18cf3112-9c98-47c1-8419-482a9db20119",
  "organization_id": "37f632eb-bfe9-4114-834f-37023b67947e",
  "name": "Q4 Cloud Infrastructure Budget",
  "allocated_amount": "5000.00",
  "spent_amount": "0.00",
  "reserved_amount": "0.00",
  "currency": "USD",
  "is_active": true
}
```

---

### Workflow 5: Autonomous Purchase Request by Agent

The agent authenticates directly using `X-Agent-API-Key`. AEON resolves agent identity from the hash, queries suppliers, executes ML recommendation, evaluates deterministic policy, and reserves budget.

```bash
curl -X POST https://aeon.app/api/v1/purchases \
  -H "X-Agent-API-Key: aeon_live_839a8df749c92138adfe91039" \
  -H "Content-Type: application/json" \
  -d '{
    "item_description": "Standard Cloud Compute Instance (8 vCPU, 32GB RAM)",
    "category": "compute",
    "max_budget": "200.00",
    "currency": "USD",
    "requirements": {
      "quantity": 1,
      "region": "us-east-1"
    }
  }'
```
**Response (201 Created):**
```json
{
  "id": "d027ca8e-06ea-4c59-bfbc-2a5438848ff3",
  "organization_id": "37f632eb-bfe9-4114-834f-37023b67947e",
  "agent_id": "c85c2c77-49db-4876-b6b6-a21239c05421",
  "item_description": "Standard Cloud Compute Instance (8 vCPU, 32GB RAM)",
  "category": "compute",
  "max_budget": "200.00",
  "currency": "USD",
  "status": "AUTHORIZED",
  "fulfillment_status": "NOT_STARTED",
  "selected_quote_id": "fa217c91-231a-4dc9-9801-b38df920aa12",
  "quotes": [
    {
      "id": "fa217c91-231a-4dc9-9801-b38df920aa12",
      "supplier_name": "MockCloudStore",
      "total_amount": "120.00",
      "currency": "USD"
    }
  ],
  "recommendation": {
    "provider_type": "mock",
    "recommended_quote_id": "fa217c91-231a-4dc9-9801-b38df920aa12",
    "reasoning": "Selected quote fa217c91 with optimal price-performance score 0.88",
    "comparison_scores": {"fa217c91": 0.88}
  },
  "policy_decision": {
    "allowed": true,
    "requires_approval": false,
    "reason_codes": ["POLICY_PASSED"],
    "approved_max_amount": "120.00"
  }
}
```

---

### Workflow 6: Human Approval Workflow

If the purchase amount exceeds `approval_threshold_amount` (e.g. $300), the status transitions to `REQUIRES_APPROVAL`.

#### 1. List Pending Approvals
```bash
curl -X GET https://aeon.app/api/v1/approvals \
  -H "Authorization: Bearer <TOKEN>"
```

#### 2. Review and Approve
```bash
curl -X POST https://aeon.app/api/v1/approvals/239a9c18-4987-43c1-90a9-1982a17ff320/decide \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "APPROVED",
    "reason": "Authorized for quarterly model training run"
  }'
```

---

### Workflow 7: PayPal Order Creation & Capture

#### 1. Create Payment Order
```bash
curl -X POST https://aeon.app/api/v1/payments/create-order \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "purchase_request_id": "d027ca8e-06ea-4c59-bfbc-2a5438848ff3"
  }'
```
**Response (201 Created):**
```json
{
  "payment_attempt_id": "67d9812a-3301-49b8-a720-3189da1098aa",
  "purchase_request_id": "d027ca8e-06ea-4c59-bfbc-2a5438848ff3",
  "provider_order_id": "ORDER-MOCK-39E3618C1D6E",
  "amount": "120.00",
  "currency": "USD",
  "status": "ORDER_CREATED",
  "approval_url": "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-MOCK-39E3618C1D6E",
  "created_at": "2026-11-10T22:10:00Z"
}
```

#### 2. Server-to-Server Capture
```bash
curl -X POST https://aeon.app/api/v1/payments/capture \
  -H "Authorization: Bearer <TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{
    "provider_order_id": "ORDER-MOCK-39E3618C1D6E"
  }'
```
**Response (200 OK):**
```json
{
  "payment_attempt_id": "67d9812a-3301-49b8-a720-3189da1098aa",
  "purchase_request_id": "d027ca8e-06ea-4c59-bfbc-2a5438848ff3",
  "provider_capture_id": "CAPTURE-MOCK-178A9C1284E1",
  "amount": "120.00",
  "currency": "USD",
  "status": "COMPLETED",
  "transaction_id": "b39a8c17-48f1-4db8-8319-38910aff3990",
  "completed_at": "2026-11-10T22:12:00Z"
}
```

---

### Workflow 8: Authoritative Payment Reconciliation

When a payment capture times out or remains in `CAPTURE_PENDING`, call the reconciliation endpoint to sync against PayPal's authoritative API:

```bash
curl -X POST https://aeon.app/api/v1/payments/ORDER-MOCK-39E3618C1D6E/reconcile \
  -H "Authorization: Bearer <TOKEN>"
```
**Response (200 OK):**
```json
{
  "id": "67d9812a-3301-49b8-a720-3189da1098aa",
  "purchase_request_id": "d027ca8e-06ea-4c59-bfbc-2a5438848ff3",
  "provider": "paypal",
  "status": "COMPLETED",
  "amount": "120.00",
  "currency": "USD",
  "provider_order_id": "ORDER-MOCK-39E3618C1D6E",
  "provider_capture_id": "CAPTURE-MOCK-178A9C1284E1",
  "created_at": "2026-11-10T22:10:00Z",
  "updated_at": "2026-11-10T22:15:00Z"
}
```

---

### Workflow 9: Dashboard & Spending Summaries

#### 1. Consolidated Overview
```bash
curl -X GET https://aeon.app/api/v1/dashboard/overview \
  -H "Authorization: Bearer <TOKEN>"
```

#### 2. Spending Analytics
```bash
curl -X GET https://aeon.app/api/v1/dashboard/spending \
  -H "Authorization: Bearer <TOKEN>"
```
**Response (200 OK):**
```json
{
  "total_spent": "120.00",
  "total_refunded": "0.00",
  "net_spent": "120.00",
  "currency": "USD",
  "by_category": {
    "compute": "120.00"
  },
  "by_supplier": {
    "MockCloudStore": "120.00"
  },
  "by_agent": [
    {
      "agent_id": "c85c2c77-49db-4876-b6b6-a21239c05421",
      "agent_name": "CloudOps-AutoProcure-Bot",
      "total_spent": "120.00",
      "purchase_count": 1
    }
  ]
}
```

#### 3. Agent Summaries
```bash
curl -X GET https://aeon.app/api/v1/dashboard/agents \
  -H "Authorization: Bearer <TOKEN>"
```

---

### Workflow 10: Financial Ledger, Receipt & Audit Trail

#### 1. Paginated Transactions
```bash
curl -X GET "https://aeon.app/api/v1/transactions?page=1&page_size=20&status=SETTLED" \
  -H "Authorization: Bearer <TOKEN>"
```

#### 2. Digital Receipt
```bash
curl -X GET https://aeon.app/api/v1/transactions/b39a8c17-48f1-4db8-8319-38910aff3990/receipt \
  -H "Authorization: Bearer <TOKEN>"
```
**Response (200 OK):**
```json
{
  "receipt_number": "REC-AEON-B39A8C17",
  "issued_at": "2026-11-10T22:12:00Z",
  "transaction_id": "b39a8c17-48f1-4db8-8319-38910aff3990",
  "organization_id": "37f632eb-bfe9-4114-834f-37023b67947e",
  "organization_name": "Acme Autonomous Corp",
  "purchase_request_id": "d027ca8e-06ea-4c59-bfbc-2a5438848ff3",
  "agent_id": "c85c2c77-49db-4876-b6b6-a21239c05421",
  "agent_name": "CloudOps-AutoProcure-Bot",
  "item_description": "Standard Cloud Compute Instance (8 vCPU, 32GB RAM)",
  "category": "compute",
  "supplier_name": "MockCloudStore",
  "quantity": 1,
  "unit_price": "120.00",
  "total_amount": "120.00",
  "currency": "USD",
  "status": "SETTLED",
  "payment_method": "PayPal Orders v2 (CAPTURE)",
  "provider_capture_id": "CAPTURE-MOCK-178A9C1284E1",
  "provider_order_id": "ORDER-MOCK-39E3618C1D6E",
  "policy_name": "Standard Cloud Procurement Policy"
}
```

#### 3. Chronological Lifecycle Timeline
```bash
curl -X GET https://aeon.app/api/v1/transactions/b39a8c17-48f1-4db8-8319-38910aff3990/timeline \
  -H "Authorization: Bearer <TOKEN>"
```
**Response (200 OK):**
```json
{
  "transaction_id": "b39a8c17-48f1-4db8-8319-38910aff3990",
  "purchase_request_id": "d027ca8e-06ea-4c59-bfbc-2a5438848ff3",
  "events": [
    {
      "id": "e1-uuid",
      "timestamp": "2026-11-10T22:05:00Z",
      "action": "PURCHASE_REQUESTED",
      "actor_type": "AGENT",
      "actor_id": "c85c2c77-49db-4876-b6b6-a21239c05421",
      "description": "Purchase request submitted by agent"
    },
    {
      "id": "e2-uuid",
      "timestamp": "2026-11-10T22:05:01Z",
      "action": "QUOTES_COLLECTED",
      "actor_type": "SYSTEM",
      "actor_id": "procurement_service",
      "description": "Supplier quotes collected and evaluated"
    },
    {
      "id": "e3-uuid",
      "timestamp": "2026-11-10T22:05:02Z",
      "action": "RECOMMENDATION_GENERATED",
      "actor_type": "SYSTEM",
      "actor_id": "ml_service",
      "description": "ML recommendation generated"
    },
    {
      "id": "e4-uuid",
      "timestamp": "2026-11-10T22:05:03Z",
      "action": "POLICY_EVALUATED",
      "actor_type": "SYSTEM",
      "actor_id": "policy_engine",
      "description": "Deterministic policy evaluated"
    },
    {
      "id": "e5-uuid",
      "timestamp": "2026-11-10T22:10:00Z",
      "action": "PAYMENT_ORDER_CREATED",
      "actor_type": "SYSTEM",
      "actor_id": "paypal_service",
      "description": "PayPal Orders v2 order created"
    },
    {
      "id": "e6-uuid",
      "timestamp": "2026-11-10T22:12:00Z",
      "action": "PAYMENT_CAPTURED",
      "actor_type": "SYSTEM",
      "actor_id": "paypal_service",
      "description": "PayPal payment successfully captured"
    }
  ]
}
```

#### 4. Audit Trail Query
```bash
curl -X GET "https://aeon.app/api/v1/audit?page=1&page_size=50&action=PAYMENT_CAPTURED" \
  -H "Authorization: Bearer <TOKEN>"
```
