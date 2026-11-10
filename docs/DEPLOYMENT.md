# AEON Backend Deployment Guide (Render + Supabase)

## 1. Prerequisites

1. A **Supabase PostgreSQL** project.
2. A **Render** account.
3. PayPal Developer Sandbox account (Client ID, Secret, Webhook ID).

---

## 2. Supabase Database Configuration

In Supabase:
1. Navigate to **Project Settings** $\rightarrow$ **Database**.
2. Locate the **Connection string** (URI).
3. The format is:
   `postgresql://postgres:[PASSWORD]@db.[PROJECT-REF].supabase.co:5432/postgres`
4. Use this URL as `DATABASE_URL` in Render. AEON automatically translates `postgresql://` to `postgresql+asyncpg://` internally.

---

## 3. Render Deployment Setup

Deploying using the provided `render.yaml`:

1. In Render Dashboard, click **New +** $\rightarrow$ **Blueprint**.
2. Connect your Git repository (`AEON`).
3. Render automatically picks up `render.yaml`.

### Manual Service Settings (if not using Blueprint):
- **Environment**: Python 3
- **Build Command**: `pip install -r requirements.txt`
- **Pre-Deploy Command**: `alembic upgrade head`
- **Start Command**:
  ```bash
  uvicorn app.main:app --host 0.0.0.0 --port $PORT
  ```
- **Health Check Path**: `/health`

> **Note on Migrations**: Running `alembic upgrade head` in `preDeployCommand` ensures migrations execute once before workers boot, avoiding concurrent migration race conditions.

---

## 4. Environment Variables Checklist

| Variable | Description | Example |
|---|---|---|
| `APP_ENV` | Application environment | `production` |
| `SECRET_KEY` | JWT signing secret (min 32 chars) | `rand-key-...` |
| `DATABASE_URL` | Supabase Postgres URL | `postgresql://postgres:...` |
| `CORS_ORIGINS` | Vercel frontend URL | `https://aeon-control.vercel.app` |
| `PAYPAL_MODE` | PayPal mode | `sandbox` |
| `PAYPAL_CLIENT_ID` | PayPal Sandbox Client ID | `AXYZ...` |
| `PAYPAL_CLIENT_SECRET`| PayPal Sandbox Secret | `EXYZ...` |
| `PAYPAL_WEBHOOK_ID` | PayPal Webhook ID | `WH-...` |
| `ML_PROVIDER_TYPE` | ML Provider (`mock` or `module`) | `mock` |

---

## 5. Verifying Deployment

1. Check liveness:
   `curl https://your-render-url.onrender.com/health`
   Should return: `{"status": "healthy", ...}`

2. Check database readiness:
   `curl https://your-render-url.onrender.com/ready`
   Should return: `{"status": "ready", "database": "connected"}`

3. Access interactive Swagger API documentation:
   `https://your-render-url.onrender.com/docs`
