# AEON React Dashboard ↔ FastAPI Integration

## Architecture boundary

The dashboard in `frontend/` is a React/Vite client for the existing Python FastAPI application. It does not start an Express server and does not ship a duplicate procurement/payment backend.

- Admin dashboard actions use `Authorization: Bearer <JWT>` from `/api/v1/auth/login` or `/api/v1/auth/register`.
- Agent purchase submission uses `X-Agent-API-Key` and calls `/api/v1/purchases`.
- Agent registration provisions the agent, policy, policy assignment and agent-scoped budget using the existing FastAPI endpoints.
- PayPal credentials remain exclusively in the Python backend environment.
- The browser return from PayPal triggers the backend `/api/v1/payments/capture` endpoint. The browser redirect itself is never treated as proof of payment.

## FastAPI endpoints used

| Frontend action | FastAPI endpoint |
|---|---|
| Health indicator | `GET /health` |
| Admin login/register/profile | `POST /api/v1/auth/login`, `POST /api/v1/auth/register`, `GET /api/v1/auth/me` |
| Agent list/create | `GET /api/v1/agents`, `POST /api/v1/agents` |
| Policy create/list/assignment | `POST /api/v1/policies`, `GET /api/v1/policies`, `POST /api/v1/policies/assignments/{agent_id}` |
| Agent budget | `POST /api/v1/budgets`, `GET /api/v1/budgets` |
| Autonomous purchase | `POST /api/v1/purchases` with `X-Agent-API-Key` |
| Human approval | `GET /api/v1/approvals`, `POST /api/v1/approvals/{approval_id}/decide` |
| PayPal order/capture/status | `POST /api/v1/payments/create-order`, `POST /api/v1/payments/capture`, `GET /api/v1/payments/{order_id}` |
| PayPal reconciliation | `POST /api/v1/payments/{order_id}/reconcile` |
| Dashboard metrics/activity | `GET /api/v1/dashboard/stats`, `GET /api/v1/dashboard/overview`, `GET /api/v1/dashboard/agents` |
| Financial ledger | `GET /api/v1/transactions`, `GET /api/v1/transactions/{id}` |
| Audit | `GET /api/v1/audit` |

The API reference remains `docs/API.md`; the dashboard client intentionally follows its `/api/v1` routes and response envelopes.

## Local setup

1. From the repository root, configure the existing Python `.env` using the root `.env.example` and your database/PayPal Sandbox credentials.
2. Install backend requirements and apply database migrations as documented in the repository README:

   ```powershell
   pip install -r requirements.txt
   alembic upgrade head
   uvicorn app.main:app --reload --port 8000
   ```

3. In a second terminal:

   ```powershell
   cd frontend
   npm install
   Copy-Item .env.example .env
   npm run dev
   ```

4. Open `http://localhost:5173`. Vite proxies `/api/*`, `/health`, `/live`, and `/ready` to `http://127.0.0.1:8000` by default. To use a different API port, set `AEON_API_PROXY_TARGET` in `frontend/.env`.
5. Register an administrator/organization or sign in with an existing administrator. The JWT is held in `sessionStorage` for the current browser tab/session.

The FastAPI backend's CORS defaults already include `http://localhost:5173`; if you change the frontend origin, add it to backend `CORS_ORIGINS`.

## Agent provisioning behaviour

The dashboard's **Create agent + policy + budget** action calls the existing backend in sequence:

1. `POST /api/v1/agents` with `name` and `description`.
2. `POST /api/v1/policies` with daily maximum, per-transaction maximum, approval threshold, supplier allow-list and `USD` currency.
3. `POST /api/v1/policies/assignments/{agent_id}` with the created policy ID.
4. `POST /api/v1/budgets` with the selected `agent_id`, allocated amount and currency.

The returned raw agent API key is issued once by FastAPI. The frontend retains it in this tab's `sessionStorage` so the workbench can submit an agent-authenticated purchase. Copy the key to your secure agent configuration when it is displayed. It is not recoverable from the API after the creation response.

The default supplier identifiers in the form match the repository API example (`mock_supplier_a`, `mock_supplier_b`). Use supplier IDs/codes that are actually registered in the backend supplier registry; display labels are not interchangeable with supplier codes.

## Purchase and payment flow

1. The workbench submits `item_description`, `category`, `max_budget`, `currency` and `requirements` to `/api/v1/purchases` using the selected agent's API key.
2. FastAPI collects supplier quotes, runs the ML adapter and deterministic policy engine, then reserves budget if authorized.
3. The dashboard displays the server recommendation, quotes and policy outcome. The LLM/recommendation layer is never treated as the authorization source.
4. The human operator continues to checkout. If a separate approval record exists, the dashboard calls the approval decision endpoint with `decision: "APPROVE"` before order creation.
5. The dashboard calls `/api/v1/payments/create-order` with `purchase_request_id` and redirects to the returned `approval_url`.
6. PayPal returns the buyer to `/payments/success?token=<PAYPAL_ORDER_ID>` or `/payments/cancel`.
7. On the success route, the frontend checks the stored payment attempt and calls `/api/v1/payments/capture` only while the attempt is in `ORDER_CREATED` or `BUYER_APPROVAL_PENDING`. It does not re-submit capture on a refresh when status is already `CAPTURE_PENDING` or `COMPLETED`.
8. A `CAPTURE_PENDING` / `PENDING_REVIEW` result remains pending and retains its budget reservation. The UI offers authoritative reconciliation through `/api/v1/payments/{order_id}/reconcile`. Only a backend-confirmed completed capture should settle funds.

## Required PayPal return/cancel configuration

The current Python settings default to `http://localhost:3000/payments/success` and `http://localhost:3000/payments/cancel`. This Vite frontend runs on port `5173`, so update the **Python backend root `.env`**:

```env
PAYPAL_RETURN_URL=http://localhost:5173/payments/success
PAYPAL_CANCEL_URL=http://localhost:5173/payments/cancel
```

Restart FastAPI after changing these settings. Do not place PayPal Client Secret or webhook ID in `frontend/.env` or any `VITE_*` variable.

## PayPal webhook URL for this backend

The Python backend webhook route is:

```text
POST /api/v1/payments/webhook
```

It is **not** the earlier Express prototype route `/api/webhooks/paypal`.

For local Sandbox testing, expose the Python backend port `8000` using ngrok:

```powershell
ngrok http 8000
```

Register/update the webhook URL in the PayPal Sandbox REST application to:

```text
https://YOUR-NGROK-HOST/api/v1/payments/webhook
```

Keep the existing four relevant PayPal subscriptions configured as supported by the Python handler, including `CHECKOUT.ORDER.APPROVED`, `PAYMENT.CAPTURE.PENDING`, `PAYMENT.CAPTURE.COMPLETED`, and capture denied/failed events. Copy the generated webhook ID into the **Python backend root `.env`** as `PAYPAL_WEBHOOK_ID`, then restart FastAPI. The frontend does not receive webhook events directly.

## Limitations / integration notes

- This ZIP intentionally contains frontend files and instructions only; it does not modify Python backend source, migrations, webhook logic or PayPal settings.
- The dashboard displays data returned by the FastAPI backend. It does not recreate the previous Express in-memory `Map` store.
- Agent API keys are retained in the current browser session. Closing the tab/session removes them; create/rotate credentials through the backend if needed.
- Supplier names, category identifiers and supplier codes must match the backend supplier registry and policy allow-list.
- Service fulfilment is separate from payment settlement. A settled PayPal transaction is not proof that a supplier delivered the service.
