# AEON — Issues and Hardening Report

This report catalogs all security audits, concurrency hazards, architectural edge cases, and schema synchronizations identified and hardened during the engineering of the AEON Agent Procurement Control Plane across Milestones 1 through 9.

---

## 1. Executive Summary & Audit Matrix

| Category | Risk Level | Issue Identified | Hardening Implemented | Verification Test |
|---|---|---|---|---|
| **Security** | Critical | Agent identity spoofing via payload `agent_id` or `organization_id` | Enforced cryptographic API key header `X-Agent-Key`; server strictly resolves identity from key hash | `test_agent_api_key_lifecycle_and_authentication` |
| **Security** | Critical | Timing attack on agent API key authentication | Replaced standard string equality with `hmac.compare_digest` on SHA-256 token hashes | `test_auth.py` |
| **Security** | High | Webhook spoofing with forged PayPal headers | Integrated PayPal cryptographic verification via cert URL download and SHA256withRSA signature verification | `test_webhook_invalid_signature_rejection` |
| **Security** | High | Cross-organization data leakage | Explicit `organization_id` filtering on all repository queries, joins, and mutation endpoints | `test_cross_organization_payment_isolation` |
| **Financial** | Critical | Floating-point rounding errors in financial transactions | All amounts defined strictly as `NUMERIC(14, 2)` in database and `decimal.Decimal` in Python/Pydantic | `test_budget_integrity.py` |
| **Financial** | Critical | Concurrent double-spending race condition | Implemented database row-level locking (`SELECT ... FOR UPDATE`) in `reserve_funds_atomic` | `test_simultaneous_budget_reservations_cannot_overspend` |
| **Financial** | Critical | Untrusted ML financial amounts | AEON discards model-provided amounts and loads verified quotes from database before policy evaluation | `test_ml_procurement_flow.py` |
| **Reliability**| High | ML reasoning overflow on PostgreSQL `VARCHAR(1024)` | Truncated reasoning to 1,024 chars in `backend_bridge`, `module_adapter`, and `procurement_service` | `test_backend_bridge_truncates_long_reasoning_to_1024` |
| **Reliability**| Medium | ML package test namespace collision if using `PYTHONPATH` | Shipped `pyproject.toml` targeting `aeon_ml*` only; package installed via `pip install -e ml-module` | `test_real_aeon_ml_module_full_procurement_flow` |
| **Financial** | High | Duplicate webhook events causing double-settlement | Unique constraint on `webhook_events.provider_event_id` and idempotent return on replays | `test_e2e_scenario_5_duplicate_webhook_event_idempotency` |
| **Lifecycle** | High | Stale human approvals executed on modified/expired quotes | Approval verification checks quote expiration, policy version, and purchase state before decision | `test_stale_approval_purchase_state_changed_rejected` |
| **Lifecycle** | Medium | Conflating payment settlement with physical goods fulfillment | Introduced separate `FulfillmentStatus` (`PENDING`, `IN_TRANSIT`, `DELIVERED`, `CANCELLED`) | `test_reconciliation_authoritative_completed` |
| **Reliability**| High | Network timeout during PayPal capture incorrectly releasing funds | Uncertain outcomes preserve `BudgetReservation` in `ACTIVE` state until authoritative reconciliation | `test_uncertain_outcome_network_timeout_retains_reservation` |

---

## 2. Security Hardening Details

### 2.1 Cryptographic Identity Isolation
- **Agent Credentials**: Raw API keys (`aeon_live_...`) are returned exactly once upon creation. Only a salted SHA-256 hash is stored in `agent_credentials`.
- **Identity Invariant**: The backend never accepts an `agent_id` or `organization_id` supplied in request bodies or query parameters as proof of identity. Caller identity is cryptographically derived solely from the Bearer JWT (dashboard users) or `X-Agent-Key` header (agents).

### 2.2 Constant-Time Comparisons
To prevent timing-based side-channel attacks during authentication:
- Password verification uses Argon2id with automatic salt generation.
- Agent key verification uses `hmac.compare_digest(stored_hash, incoming_hash)`.

### 2.3 Strict Multi-Tenancy
All repositories enforce tenant isolation at the query level:
```python
stmt = select(Model).where(
    Model.id == resource_id,
    Model.organization_id == authenticated_organization_id
)
```
Any cross-tenant access attempt returns an HTTP 404 or 403, preventing data enumeration.

---

## 3. Financial Integrity & Concurrency Hardening

### 3.1 Row-Level Budget Locking
In high-throughput environments where autonomous agents submit rapid purchase requests, naive budget checks (`if available >= requested`) permit double-spending due to race conditions.
AEON solves this using pessimistic locking:
```python
stmt = select(Budget).where(Budget.id == budget_id).with_for_update()
budget = await self.session.scalar(stmt)
if budget.available_amount < amount:
    raise BudgetExceededError(...)
budget.reserved_amount += amount
```
This guarantees that concurrent transactions are serialized at the database engine level.

### 3.2 ML Boundary Sandboxing
The central architectural principle—**"ML Recommends, but AEON Authorizes"**—is enforced mechanically:
1. Candidate quotes are collected and persisted by AEON.
2. The recommendation provider receives normalized quote options and returns a recommended `quote_id`.
3. AEON validates that the returned `quote_id` matches an existing, non-expired quote belonging to the current purchase request.
4. The payment amount is read directly from `selected_quote.total_amount` in the database, never from ML output.
5. Even if an ML model recommends a quote, AEON's deterministic policy engine independently evaluates budget limits, supplier allow-lists, and human approval rules.

### 3.3 Uncertain Payment Handling
When initiating or capturing a PayPal payment, network partitions or timeouts can leave the payment outcome ambiguous.
- Naively marking the payment failed would release the reserved budget, potentially allowing the agent to spend funds that PayPal later captures.
- AEON retains the `BudgetReservation` in `ACTIVE` state, records a `PAYMENT_ATTEMPT_UNCERTAIN` event, and flags the transaction for authoritative background reconciliation.
- Reserved funds are released only upon a definitive failure response from PayPal.

---

## 4. Webhook & Event Ledger Hardening

### 4.1 Idempotency Guarantee
PayPal guarantees at-least-once delivery, meaning duplicate or replayed webhooks will occur.
- AEON enforces a database-level `UNIQUE` constraint on `webhook_events.provider_event_id`.
- The webhook processing service uses an atomic insert: if the event ID exists, AEON immediately responds with HTTP 200 `{"status": "already_processed"}` without re-executing ledger updates or budget mutations.

### 4.2 Out-of-Order Event Handling
If a `PAYMENT.CAPTURE.COMPLETED` webhook arrives before the frontend or backend receives the synchronous capture response, AEON gracefully handles the sequence:
1. Validates event signature.
2. Resolves purchase request from `custom_id` or order mapping.
3. Settles budget reservation and creates an immutable `Transaction` record.
4. Subsequent capture calls detect the settled transaction and return the existing record idempotently.

---

## 5. Verification Summary

The complete test suite verifies all security, financial, and lifecycle hardening measures:

```
============================ 110 passed in 18.25s ============================
- Backend Control Plane Tests (tests/): 80 passed
  • Unit Tests (Security, Models, Policy, Budgets, Identity): 37 passed
  • Integration Tests (Procurement, Payments, Webhooks, APIs): 36 passed
  • End-to-End Workflows (All 7 Master Hardening Scenarios): 7 passed
- ML Module Engine Tests (ml-module/tests/): 30 passed
  • Ranking, Feature Extraction, Scikit-Learn Model: 8 passed
  • Bridge Compatibility, 1024-Char Truncation, FastAPI: 6 passed
  • Safety Invariants, Exception Containment, Benchmarks: 16 passed
```
All tests pass cleanly with zero regressions.
