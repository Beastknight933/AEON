# AEON Backend Deployment Guide (Render + Supabase + Vercel)

This guide provides end-to-end instructions for deploying the AEON Agent Procurement Control Plane backend to **Render**, connecting to **Supabase PostgreSQL**, configuring **PayPal Sandbox** webhooks, and integrating with the external **Vercel** frontend.

---

## 1. Architecture & Infrastructure Topology

```
                  ┌───────────────────────────────────────────┐
                  │          Vercel Frontend (SPA)            │
                  │        https://aeon-control.vercel.app    │
                  └─────────────────────┬─────────────────────┘
                                        │ HTTPS / CORS
                                        ▼
                  ┌───────────────────────────────────────────┐
                  │            Render Web Service             │
                  │         (FastAPI / Uvicorn / Python 3.12) │
                  │      https://aeon-backend.onrender.com    │
                  └───┬───────────────────────────────┬───────┘
                      │                               │
             asyncpg  │                               │ PayPal REST API v2
         Port 5432/   ▼                               ▼ & Webhook Verifier
  ┌───────────────────────────────┐     ┌────────────────────────────────┐
  │      Supabase PostgreSQL      │     │      PayPal Developer Portal   │
  │     (Row-Level Lock Pools)    │     │       (Sandbox Environment)    │
  └───────────────────────────────┘     └────────────────────────────────┘
```

---

## 2. Supabase PostgreSQL Configuration

### Connection String Strategy
Supabase offers two connection endpoints:
1. **Connection Pooler / Session Mode (Port 5432 - REQUIRED FOR RENDER)**:
   - Render does not support outbound IPv6 traffic. Because direct Supabase hosts (`db.[REF].supabase.co`) resolve exclusively to IPv6 addresses, connecting directly from Render results in `OSError: [Errno 101] Network is unreachable`.
   - **Render must use the Supabase Connection Pooler IPv4 hostname** in Session mode (port `5432`):
     ```
     postgresql+asyncpg://postgres.[PROJECT-REF]:[PASSWORD]@aws-0-[REGION].pooler.supabase.com:5432/postgres
     ```
   - Session mode pooler fully supports row-level locking (`SELECT ... FOR UPDATE`), transaction isolation, and Alembic migrations.

2. **Transaction Pooler (Port 6543)**:
   - Port `6543` can also be used; AEON automatically sets `statement_cache_size = 0` when connecting to `pooler.supabase.com` to prevent prepared statement collisions.

3. **Direct Connection (Port 5432 - IPv6 only)**:
   - URI format: `postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres`
   - Only works on hosts with native IPv6 egress or with Supabase's paid IPv4 add-on. Do not use on Render.

### Database Preparation
No manual SQL script execution is required. Database schema creation is fully automated via Alembic migrations.

---

## 3. Render Deployment Setup

### Blueprint Deployment (Fastest)
AEON includes a validated `render.yaml` infrastructure-as-code specification.

1. Navigate to your [Render Dashboard](https://dashboard.render.com).
2. Click **New +** $\rightarrow$ **Blueprint**.
3. Connect your GitHub repository (`AEON`).
4. Render will parse `render.yaml` and configure:
   - **Service Name**: `aeon-backend`
   - **Environment**: `python` (Python 3.12.10)
   - **Plan**: `free` (or `starter`)
   - **Build Command**: `pip install -r requirements.txt && pip install ./ml-module`
   - **Start Command**: `bash scripts/start.sh`
   - **Health Check Path**: `/health`

> **Free Tier Pre-Deployment Execution**: Render's free tier does not support isolated `preDeployCommand` hooks. AEON addresses this via `scripts/start.sh`, which automatically applies all Alembic database migrations (`alembic upgrade head`) before invoking the Uvicorn ASGI server. Optionally, set `AUTO_SEED=true` in Render environment variables on initial deployment to automatically seed the admin user, sample agents, and default policies.

### Required Environment Variables in Render Dashboard
Under the **Environment** tab of the `aeon-backend` service, populate the secret keys:

| Environment Variable | Description | Example / Instructions |
|---|---|---|
| `APP_ENV` | Application environment | `production` |
| `SECRET_KEY` | Dashboard JWT signing secret (min 32 chars) | Click **Generate** or supply random 64-char string |
| `DATABASE_URL` | Supabase Postgres URL | `postgresql://postgres:[PASSWORD]@db.[REF].supabase.co:5432/postgres` |
| `CORS_ORIGINS` | Permitted frontend origins (comma-separated) | `https://aeon-control.vercel.app,http://localhost:3000` |
| `PAYPAL_MODE` | PayPal SDK mode | `sandbox` |
| `PAYPAL_CLIENT_ID` | PayPal Sandbox App Client ID | From PayPal Developer Dashboard |
| `PAYPAL_CLIENT_SECRET` | PayPal Sandbox App Secret | From PayPal Developer Dashboard |
| `PAYPAL_WEBHOOK_ID` | PayPal Registered Webhook ID | Generated after webhook registration (see Section 4) |
| `PAYPAL_RETURN_URL` | Frontend buyer approval redirect | `https://aeon-control.vercel.app/payments/success` |
| `PAYPAL_CANCEL_URL` | Frontend buyer cancellation redirect | `https://aeon-control.vercel.app/payments/cancel` |
| `ML_PROVIDER_TYPE` | ML Provider selector (`mock` or `module`) | `mock` (or `module` to activate the hybrid ML ranker) |
| `ML_MODULE_PATH` | Import path for ML engine | `aeon_ml` |

---

## 4. PayPal Sandbox Webhook Registration

To enable asynchronous payment confirmation and reconciliation:

1. Log in to [PayPal Developer Dashboard](https://developer.paypal.com/dashboard/).
2. Select **Apps & Credentials** $\rightarrow$ toggle to **Sandbox** $\rightarrow$ select your REST App.
3. Under **Webhooks**, click **Add Webhook**.
4. Enter the public Render webhook URL:
   ```
   https://<your-render-app>.onrender.com/api/v1/payments/webhook
   ```
5. Select the following event triggers:
   - `CHECKOUT.ORDER.APPROVED`
   - `PAYMENT.CAPTURE.COMPLETED`
   - `PAYMENT.CAPTURE.DENIED`
   - `PAYMENT.CAPTURE.REFUNDED`
   - `PAYMENT.CAPTURE.REVERSED`
6. Click **Save**. Copy the generated **Webhook ID** (e.g., `WH-4PL78912KL345678X`) and set it as `PAYPAL_WEBHOOK_ID` in your Render Environment Variables.

---

## 5. Initial Production Database Seeding

Once the service is deployed and migrations have completed:

1. Open the **Shell** tab in the Render Dashboard for `aeon-backend`.
2. Run the seed script:
   ```bash
   python scripts/seed.py
   ```
3. The seed script idempotently creates:
   - Default organization: **Acme Corp**
   - Admin account: `admin@aeon.local` / `AdminPass123!`
   - Approver account: `approver@aeon.local` / `ApproverPass123!`
   - Standard member: `member@aeon.local` / `MemberPass123!`
   - Default autonomous agent: `AutoBuyer-Alpha`
   - Pre-generated agent key: `aeon_live_sample_secret_key_12345`
   - Standard organization policy: $100 auto-approval threshold, $500 per-transaction cap
   - Q1 Compute budget: $10,000.00
   - Mock suppliers: `CloudCore Services` and `ByteScale Infrastructure`

---

## 6. Verification and Health Probes

Verify deployment health using `curl`:

### 1. Liveness Probe
```bash
curl -I https://<your-render-app>.onrender.com/health
# or
curl -I https://<your-render-app>.onrender.com/live
```
**Expected Response**: `HTTP/1.1 200 OK`
```json
{"status": "healthy", "app": "AEON - Agent Procurement Control Plane", "environment": "production"}
```

### 2. Readiness Probe (Checks Live Supabase Connection)
```bash
curl -s https://<your-render-app>.onrender.com/ready
```
**Expected Response**: `HTTP/1.1 200 OK`
```json
{"status": "ready", "database": "connected"}
```

### 3. Interactive Documentation
Navigate to `https://<your-render-app>.onrender.com/docs` to test endpoints via Swagger UI.

---

## 7. Frontend Integration Checklist (Vercel)

The frontend developer should set the following environment variable in Vercel:

```env
VITE_API_BASE_URL=https://<your-render-app>.onrender.com/api/v1
```

AEON automatically handles CORS headers for the configured Vercel domain, supports credentialed requests, and exposes `X-Correlation-ID` for end-to-end request tracing.
