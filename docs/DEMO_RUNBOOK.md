# AEON — Master Demo Runbook

This runbook guides evaluators, engineers, and stakeholders through a live demonstration of AEON's capabilities across the complete agent procurement lifecycle.

All scenarios can be executed against a running instance (`http://localhost:8000` or deployed on Render) using standard `curl` commands or through the automated E2E test suite.

---

## 0. Quick Automated Demo

To run the complete automated test suite covering all 7 master E2E scenarios:

```bash
pytest tests/e2e/test_master_e2e_workflows.py -v
```

All 7 core invariants will be verified within ~1.5 seconds.

To verify the in-process `aeon_ml` hybrid ranker end-to-end procurement flow:
```bash
pytest tests/integration/test_ml_procurement_flow.py -k "test_real_aeon_ml_module_full_procurement_flow" -v
```

To run all 110 automated tests (control plane and ML engine):
```bash
pytest tests ml-module/tests -v
```

---

## 1. Demo Credentials & Environment

If starting from a seeded database (`python scripts/seed.py`), the following default credentials are pre-configured:

| Identity | Type | Value / Credentials | Role / Notes |
|---|---|---|---|
| **Admin User** | Human | `admin@aeon.local` / `AdminPass123!` | Full Org Admin permissions |
| **Approver User** | Human | `approver@aeon.local` / `ApproverPass123!` | Procurement Approver permissions |
| **Agent Key** | AI Agent | `aeon_live_sample_secret_key_12345` | AutoBuyer-Alpha |
| **Org Policy** | Policy | Max $500/tx, $100 Approval Threshold | Allow-list: CLOUD_CORE, BYTESCALE |
| **Org Budget** | Budget | $10,000.00 allocated | Available for reservations |

### Base URL Definition
```bash
export AEON_URL="http://localhost:8000/api/v1"
```

---

## Scenario 1: Agent Authentication & Autonomous Approved Purchase

**Objective**: An AI agent submits a purchase request within its policy limits ($40.00 storage). AEON collects quotes, gets ML recommendation, deterministically authorizes the purchase, and reserves budget atomically.

### 1.1 Obtain Admin JWT (for verification)
```bash
ADMIN_TOKEN=$(curl -s -X POST "$AEON_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@aeon.local","password":"AdminPass123!"}' \
  | jq -r '.access_token')
echo "Admin Token: $ADMIN_TOKEN"
```

### 1.2 Agent Submits Purchase Request
```bash
PURCHASE_RES=$(curl -s -X POST "$AEON_URL/purchases" \
  -H "X-Agent-Key: aeon_live_sample_secret_key_12345" \
  -H "Content-Type: application/json" \
  -d '{
    "item_description": "Standard Storage Volume 500GB",
    "category": "storage",
    "max_budget": "60.00",
    "currency": "USD",
    "requirements": {"storage_gb": 500}
  }')
echo $PURCHASE_RES | jq .
PURCHASE_ID=$(echo $PURCHASE_RES | jq -r '.id')
```

### 1.3 Expected Output & Verification
- Status: `AUTHORIZED`
- Selected Quote: ~$40.00
- Policy Decision: `allowed = true`, `requires_approval = false`
- Budget: $40.00 reserved in `ACTIVE` state.

---

## Scenario 2: Deterministic Policy Violation Rejection

**Objective**: An AI agent attempts to purchase an item that exceeds the organization's per-transaction limit ($500.00). AEON's deterministic engine instantly blocks the purchase and prevents any budget reservation.

### 2.1 Agent Submits Over-Budget Request
```bash
curl -s -X POST "$AEON_URL/purchases" \
  -H "X-Agent-Key: aeon_live_sample_secret_key_12345" \
  -H "Content-Type: application/json" \
  -d '{
    "item_description": "Enterprise GPU Server",
    "category": "compute",
    "max_budget": "800.00",
    "currency": "USD",
    "requirements": {"gpus": 4}
  }' | jq .
```

### 2.2 Expected Output & Verification
- Status: `BLOCKED`
- Policy Decision: `allowed = false`
- Reason Codes: `["PER_TRANSACTION_LIMIT_EXCEEDED"]`
- Invariant: Zero funds reserved; no human approval requested.

---

## Scenario 3: Human-in-the-Loop Approval Workflow

**Objective**: An AI agent submits a purchase for ~$120.00 (within $500 max cap, but above $100 auto-approval threshold). AEON reserves budget and transitions purchase to `REQUIRES_APPROVAL`. A human approver reviews and approves or rejects the request.

### 3.1 Agent Submits Request Requiring Approval
```bash
PR_APP_RES=$(curl -s -X POST "$AEON_URL/purchases" \
  -H "X-Agent-Key: aeon_live_sample_secret_key_12345" \
  -H "Content-Type: application/json" \
  -d '{
    "item_description": "Dedicated Compute Cluster",
    "category": "compute",
    "max_budget": "200.00",
    "currency": "USD",
    "requirements": {"instances": 2}
  }')
echo $PR_APP_RES | jq .
APPROVAL_PURCHASE_ID=$(echo $PR_APP_RES | jq -r '.id')
```

### 3.2 Human Approver Views Pending Approvals
```bash
APPROVER_TOKEN=$(curl -s -X POST "$AEON_URL/auth/login" \
  -H "Content-Type: application/json" \
  -d '{"email":"approver@aeon.local","password":"ApproverPass123!"}' \
  | jq -r '.access_token')

PENDING_APPROVALS=$(curl -s -X GET "$AEON_URL/approvals" \
  -H "Authorization: Bearer $APPROVER_TOKEN")
echo $PENDING_APPROVALS | jq .
APPROVAL_ID=$(echo $PENDING_APPROVALS | jq -r '.[0].id')
```

### 3.3 Human Approver Approves or Rejects Request
To Approve:
```bash
curl -s -X POST "$AEON_URL/approvals/$APPROVAL_ID/decide" \
  -H "Authorization: Bearer $APPROVER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "APPROVE",
    "notes": "Approved for Q1 data processing workload."
  }' | jq .
```
- Purchase status transitions from `REQUIRES_APPROVAL` to `AUTHORIZED`.

*(Or to Reject)*:
```bash
curl -s -X POST "$AEON_URL/approvals/$APPROVAL_ID/decide" \
  -H "Authorization: Bearer $APPROVER_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "decision": "REJECT",
    "notes": "Cost exceeds current project allocation."
  }' | jq .
```
- Purchase transitions to `CANCELLED`, and budget reservation is atomically `RELEASED`.

---

## Scenario 4: PayPal Payment Creation & Capture

**Objective**: For an `AUTHORIZED` purchase, initiate PayPal payment order creation (`intent=CAPTURE`), retrieve the PayPal buyer approval URL, and execute server-to-server capture.

### 4.1 Create PayPal Order
```bash
ORDER_RES=$(curl -s -X POST "$AEON_URL/payments/create-order" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"purchase_request_id\": \"$PURCHASE_ID\"}")
echo $ORDER_RES | jq .
PROVIDER_ORDER_ID=$(echo $ORDER_RES | jq -r '.provider_order_id')
APPROVAL_URL=$(echo $ORDER_RES | jq -r '.approval_url')
echo "Buyer Approval URL: $APPROVAL_URL"
```

### 4.2 Server-to-Server Capture Order
```bash
CAPTURE_RES=$(curl -s -X POST "$AEON_URL/payments/capture" \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d "{\"provider_order_id\": \"$PROVIDER_ORDER_ID\"}")
echo $CAPTURE_RES | jq .
```

### 4.3 Expected Output & Financial Settlement
- Status: `COMPLETED`
- Purchase Status: `COMPLETED`
- Fulfillment Status: `PENDING`
- Budget Reservation: `SETTLED` (reserved amount decremented, spent amount incremented)
- Immutable Transaction: Recorded in financial ledger with PayPal capture ID.

---

## Scenario 5: Webhook Signature Verification & Idempotency

**Objective**: Test PayPal webhook ingestion, signature validation, duplicate replay prevention, and authoritative reconciliation.

### 5.1 Ingest Verified Webhook Event
```bash
curl -s -X POST "$AEON_URL/payments/webhook" \
  -H "paypal-transmission-id: trans-demo-001" \
  -H "paypal-transmission-time: $(date -u +"%Y-%m-%dT%H:%M:%SZ")" \
  -H "paypal-cert-url: https://api.paypal.com/cert" \
  -H "paypal-auth-algo: SHA256withRSA" \
  -H "paypal-transmission-sig: valid_signature" \
  -H "Content-Type: application/json" \
  -d '{
    "id": "WH-DEMO-EVT-001",
    "event_type": "PAYMENT.CAPTURE.COMPLETED",
    "resource": {
      "id": "CAP-DEMO-999",
      "status": "COMPLETED",
      "custom_id": "'"$PURCHASE_ID"'"
    }
  }' | jq .
```

### 5.2 Resend Exact Same Webhook (Duplicate Protection)
Executing the identical `curl` command above returns:
```json
{
  "status": "already_processed",
  "provider_event_id": "WH-DEMO-EVT-001"
}
```
The financial ledger remains untouched, preventing double-crediting or duplicate transaction entries.

---

## Scenario 6: Dashboard Overview & Audit Trail Inspection

**Objective**: Inspect the aggregated spending metrics, agent summary cards, transaction timelines, and immutable audit logs provided for the external frontend.

### 6.1 Dashboard Overview Metrics
```bash
curl -s -X GET "$AEON_URL/dashboard/overview" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
```

### 6.2 Agent Spending Summary
```bash
curl -s -X GET "$AEON_URL/dashboard/agents" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
```

### 6.3 Transaction History (Paginated)
```bash
curl -s -X GET "$AEON_URL/transactions?page=1&page_size=10" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
```

### 6.4 Immutable Audit Trail
```bash
curl -s -X GET "$AEON_URL/audit?page=1&page_size=20" \
  -H "Authorization: Bearer $ADMIN_TOKEN" | jq .
```

---

## Summary of Guarantees Demonstrated

| Invariant | Mechanism Verified |
|---|---|
| **Zero ML Authority** | ML recommendation was checked against database quotes and subjected to deterministic policy evaluation. |
| **Atomic Budget Locks** | Reservations and releases strictly synchronized using row-level database locking. |
| **Human Approver Limits** | Approvers cannot override hard policy caps; rejections automatically release reserved capital. |
| **Financial Ledger Integrity** | Payments create immutable `Transaction` records with unique provider capture IDs and idempotency keys. |
| **Strict Multi-Tenancy** | Every transaction, agent, policy, and audit log is strictly bounded to the authenticated organization. |
