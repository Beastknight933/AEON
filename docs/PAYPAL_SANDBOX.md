# AEON PayPal Sandbox Payment Integration Guide

This document describes the PayPal Orders v2 integration implemented for **AEON (Agent Procurement Control Plane)** in Milestone 6.

---

## 1. Architectural Principles

AEON governs purchases initiated by autonomous AI agents. The payment subsystem enforces strict financial and security boundaries:

1. **Deterministic Preconditions**:
   Only purchase requests with status `AUTHORIZED` and an `ACTIVE` budget reservation can create payment orders or execute captures.
2. **Never Trust Browser Redirects**:
   The buyer return URL (`PAYPAL_RETURN_URL`) is merely a UI navigation callback containing query parameters (`token`, `PayerID`). It is **never** accepted as proof of payment. Payment is only settled when the backend executes a verified server-to-server capture with PayPal or processes a cryptographically verified webhook event.
3. **Database-Derived Payable Amounts**:
   Payment amounts are loaded directly from the database quote bound to the authorized purchase request. Neither agent input, frontend input, nor ML model output can alter the payable amount.
4. **Idempotency Everywhere**:
   All PayPal Orders v2 mutation calls transmit a unique `PayPal-Request-Id`. Duplicate capture requests return existing settlement state without duplicate ledger entries or double-spending.
5. **Fail-Safe Budget Reservation**:
   Uncertain outcomes (such as network timeouts during capture) must **never** release reserved budget funds or falsely mark payments complete. Reserved funds are retained in `CAPTURE_PENDING` until definitive reconciliation.

---

## 2. Procurement & Payment Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor Admin as Admin / Approver
    participant AEON as AEON Control Plane
    participant DB as Supabase PostgreSQL
    participant PP as PayPal Orders v2 API
    actor Buyer as Buyer / User

    Note over Admin,AEON: 1. Purchase is AUTHORIZED with ACTIVE Reservation
    Admin->>AEON: POST /api/v1/payments/create-order {purchase_request_id}
    AEON->>DB: Verify AUTHORIZED status & ACTIVE budget reservation
    AEON->>PP: POST /v2/checkout/orders (intent: CAPTURE, PayPal-Request-Id)
    PP-->>AEON: 201 Created (order_id, approve_url)
    AEON->>DB: Insert PaymentAttempt (status: ORDER_CREATED)
    AEON-->>Admin: 201 Created (provider_order_id, approval_url)

    Admin->>Buyer: Direct to approval_url
    Buyer->>PP: Approves checkout
    PP-->>Buyer: Redirects to return_url?token=ORDER_ID&PayerID=XYZ

    Note over Buyer,AEON: 2. Server-to-Server Capture (Proof of Payment)
    Admin->>AEON: POST /api/v1/payments/capture {provider_order_id}
    AEON->>DB: Lock PaymentAttempt (status -> CAPTURE_PENDING)
    AEON->>PP: POST /v2/checkout/orders/{order_id}/capture (PayPal-Request-Id)
    
    alt PayPal Capture Succeeds (COMPLETED)
        PP-->>AEON: 201 Completed (capture_id)
        AEON->>DB: Settle budget reservation atomically (reserved -> spent)
        AEON->>DB: Insert Transaction (status: SETTLED, type: PURCHASE)
        AEON->>DB: PurchaseRequest status -> COMPLETED
        AEON->>DB: PaymentAttempt status -> COMPLETED
        AEON-->>Admin: 200 OK (provider_capture_id, transaction_id)
    else Network Timeout / Uncertain Error
        PP--xAEON: ReadTimeout / 5xx Network Error
        AEON->>DB: PaymentAttempt status remains CAPTURE_PENDING
        Note over AEON,DB: ACTIVE budget reservation is RETAINED!
        AEON-->>Admin: 400 Bad Request (Outcome uncertain; reservation retained)
    else Definitive Failure (DECLINED / FAILED)
        PP-->>AEON: Status: DECLINED
        AEON->>DB: PaymentAttempt status -> FAILED
        AEON->>DB: Release budget reservation atomically (reserved -> available)
        AEON->>DB: PurchaseRequest status -> CANCELLED
        AEON-->>Admin: 400 Bad Request (Capture failed)
    end
```

---

## 3. Configuration & Environment Variables

Configure the following variables in your `.env` or deployment environment:

| Variable | Description | Example (Sandbox) |
|---|---|---|
| `PAYPAL_CLIENT_ID` | OAuth2 Client ID from PayPal Developer Portal | `A...` |
| `PAYPAL_CLIENT_SECRET` | OAuth2 Client Secret | `E...` |
| `PAYPAL_API_BASE_URL` | Base API endpoint URL | `https://api-m.sandbox.paypal.com` |
| `PAYPAL_RETURN_URL` | Frontend URL redirected to after buyer approval | `https://aeon.app/checkout/return` |
| `PAYPAL_CANCEL_URL` | Frontend URL redirected to if buyer cancels | `https://aeon.app/checkout/cancel` |
| `PAYPAL_WEBHOOK_ID` | Webhook ID registered in developer portal | `WH-987654321` |

---

## 4. PayPal Sandbox Developer Account Setup

1. Log in to the [PayPal Developer Dashboard](https://developer.paypal.com/).
2. Under **Testing Tools** > **Sandbox Accounts**:
   - Ensure a **Business (Facilitator)** account exists (e.g. `sb-facilitator@business.example.com`).
   - Ensure a **Personal (Buyer)** account exists with funded balance (e.g. `sb-buyer@personal.example.com`).
3. Under **Apps & Credentials**:
   - Toggle to **Sandbox** mode.
   - Click **Create App** (named `AEON Control Plane`).
   - Copy the generated `Client ID` and `Secret` to `PAYPAL_CLIENT_ID` and `PAYPAL_CLIENT_SECRET`.
4. Under **Webhooks**:
   - Add a webhook pointing to `https://<YOUR_RENDER_URL>/api/v1/payments/webhook`.
   - Subscribe to events:
     - `CHECKOUT.ORDER.APPROVED`
     - `PAYMENT.CAPTURE.COMPLETED`
     - `PAYMENT.CAPTURE.DENIED`
     - `PAYMENT.CAPTURE.REFUNDED`
   - Copy the webhook ID to `PAYPAL_WEBHOOK_ID`.

---

## 5. API Reference

### 5.1 Create Payment Order
- **Endpoint**: `POST /api/v1/payments/create-order`
- **Auth**: Admin or Approver JWT token
- **Request Body**:
  ```json
  {
    "purchase_request_id": "8fa887f4-d023-41bb-a579-2de13b4fca89"
  }
  ```
- **Response** (`201 Created`):
  ```json
  {
    "payment_attempt_id": "7df4a8f9-4b6a-4d2c-8069-b570e30bb733",
    "purchase_request_id": "8fa887f4-d023-41bb-a579-2de13b4fca89",
    "provider_order_id": "ORDER-MOCK-39E3618C1D6E",
    "amount": "120.00",
    "currency": "USD",
    "status": "ORDER_CREATED",
    "approval_url": "https://www.sandbox.paypal.com/checkoutnow?token=ORDER-MOCK-39E3618C1D6E",
    "created_at": "2026-11-10T21:45:00Z"
  }
  ```

### 5.2 Capture Payment
- **Endpoint**: `POST /api/v1/payments/capture`
- **Auth**: Admin or Approver JWT token
- **Request Body**:
  ```json
  {
    "provider_order_id": "ORDER-MOCK-39E3618C1D6E"
  }
  ```
- **Response** (`200 OK`):
  ```json
  {
    "payment_attempt_id": "7df4a8f9-4b6a-4d2c-8069-b570e30bb733",
    "purchase_request_id": "8fa887f4-d023-41bb-a579-2de13b4fca89",
    "provider_capture_id": "CAPTURE-MOCK-178A9C1284E1",
    "amount": "120.00",
    "currency": "USD",
    "status": "COMPLETED",
    "transaction_id": "1bc96711-e409-4ce3-a2e9-74d1a10debe3",
    "completed_at": "2026-11-10T21:45:02Z"
  }
  ```

### 5.3 Query Payment Status
- **Endpoint**: `GET /api/v1/payments/{provider_order_id}`
- **Auth**: Admin or Approver JWT token

### 5.4 PayPal Webhook Receiver
- **Endpoint**: `POST /api/v1/payments/webhook`
- **Auth**: Public (verifies cryptographic PayPal headers)

---

## 6. Injectable Mock Adapter & Testing

For fast, isolated testing without real network calls or sandbox accounts, AEON provides `MockPayPalClient`:

```python
from app.integrations.paypal.client import MockPayPalClient, set_paypal_client

# 1. Normal mock testing
mock_client = MockPayPalClient()
set_paypal_client(mock_client)

# 2. Simulate capture network timeout (tests uncertain outcome invariant)
timing_out_client = MockPayPalClient(should_timeout_capture=True)
set_paypal_client(timing_out_client)

# 3. Simulate declined capture (tests automatic budget reservation release)
declining_client = MockPayPalClient(should_fail_capture=True)
set_paypal_client(declining_client)
```

In `APP_ENV=testing` mode or when `PAYPAL_CLIENT_ID` starts with `mock_`, the default `PayPalClient` automatically runs in mock mode, returning simulated orders and captures while preserving all database schemas, constraints, and audit logging.
