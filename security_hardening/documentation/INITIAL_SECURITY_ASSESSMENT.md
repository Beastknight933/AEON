# AEON — Initial Security Discovery & Enterprise Hardening Assessment

**Date**: November 2026  
**Target Application**: AEON Autonomous Agent Procurement Control Plane  
**Operating Environment**: Production (Render Web Service + Supabase PostgreSQL + Vercel Frontend)  
**Security Classification**: Enterprise Financial Control Plane / High-Value Autonomous Transactions  
**Document Status**: Phase 1 Discovery & Baseline Audit Complete  

---

## 1. Executive Summary & Context

AEON is an enterprise-grade autonomous procurement control plane designed to govern, inspect, and authorize corporate financial transactions initiated by autonomous AI agents. The central governing philosophy of the architecture is:

> **"ML Recommends, but AEON Authorizes. The Backend Ledger is Authoritative."**

The platform is already developed, tested, and actively hosted across Render (`https://aeon-m136.onrender.com`), Supabase PostgreSQL (`aws-0-*.pooler.supabase.com:5432`), and Vercel (`https://aeon-control.vercel.app`). 

This assessment establishes the technical baseline, catalogs all existing security guarantees, identifies latent vulnerabilities and architectural risks, and outlines an enterprise security hardening strategy that strictly obeys the **Zero-Disruption Invariant**:
- The running application must not be taken offline or restarted.
- Existing API contracts, routes, schemas, database tables, and business logic must remain 100% backward-compatible.
- All new security controls, cryptosystems, audit chaining, fraud detection engines, and tests reside in the dedicated `security_hardening/` directory.

---

## 2. Technology Stack & Component Inventory

| Layer | Component | Technologies & Frameworks | Version / Constraints |
| :--- | :--- | :--- | :--- |
| **Backend API Gateway** | Web Engine & Routers | Python 3.12+, FastAPI, Uvicorn, Starlette, Pydantic v2 | 11 Domain Routers (`/api/v1/...`) |
| **Database & Persistence** | Relational Ledger & Storage | PostgreSQL (Supabase Session Pooler), SQLAlchemy 2.x async (`asyncpg`), SQLite dev (`aiosqlite`), Alembic | 19 Relational Entities, UUID Primary Keys |
| **Authentication & IAM** | Dual Auth Engines | Argon2id (`argon2-cffi`), PyJWT (HS256), SHA-256 HMAC constant-time matching | Human RBAC + Agent API Key (`aeon_live_*`) |
| **ML Engine** | In-Process Hybrid Ranker | `aeon_ml`, scikit-learn, Multi-Attribute Utility Theory (MAUT), NumPy | Static JSON model artifact (`preference_model.json`) |
| **Payment Gateway** | Settlement Engine | PayPal Orders v2 REST API (OAuth2 Client Credentials, Webhook Signature Verification) | Intent: CAPTURE, Idempotency headers |
| **Frontend** | Governance Console | React 18, TypeScript, Vite 6, Tailwind CSS, AG Grid Community, Recharts | Dual-mode: Backend REST vs. Demo Mode |
| **Hosting & Cloud** | Infrastructure | Render Web Service (FastAPI), Supabase (PostgreSQL pooler), Vercel (SPA) | Fully deployed and confirmed active |

---

## 3. Inventory of Existing 22 Security Features

The initial audit confirmed that the AEON platform already implements 22 baseline security features:

1. **Argon2id Administrator Password Hashing**: Utilizes memory-hard and GPU-resistant Argon2id via `argon2-cffi`.
2. **Stateless JWT Access Tokens**: HS256 signed access tokens with 60-minute default expiration containing `sub`, `org_id`, and `role`.
3. **Cryptographically Secure Agent API Keys**: Generated via `secrets.token_urlsafe(32)` prefixed with `aeon_live_` (256-bit entropy).
4. **One-Time Agent API Key Exposure**: Raw plaintext keys are returned strictly once upon generation/rotation and are never logged or persisted.
5. **Constant-Time Key Hash Matching**: Candidate lookup uses indexed 16-character `key_prefix`; verification compares SHA-256 hashes using `hmac.compare_digest`.
6. **Zero-Trust Agent Identity Resolution**: Server derives caller identity exclusively from verified API key hashes; caller-supplied `agent_id` or `organization_id` in request payloads are discarded.
7. **Strict Multi-Tenancy & Data Isolation**: All repository queries and mutations strictly filter on `organization_id`.
8. **Role-Based Access Control (RBAC)**: Enforces `ADMIN`, `APPROVER`, and `MEMBER` roles using FastAPI route dependencies (`require_roles`).
9. **Deterministic Hard-Policy Enforcement**: Hard non-negotiable policy constraints evaluated mechanically before any fund reservation.
10. **Supplier Allow-Lists & Per-Transaction Limits**: Enforces verified supplier allow-lists and ceiling limits on single transactions.
11. **Rolling 24-Hour Spending Limits**: Tracks cumulative agent spend and reservations over the preceding 24 hours.
12. **Database Row-Level Pessimistic Locking**: `SELECT ... FOR UPDATE` (`with_for_update()`) serializes concurrent budget reservations to eliminate double-spending race conditions.
13. **Exact Decimal Financial Arithmetic**: Strict use of Python `decimal.Decimal` and PostgreSQL `NUMERIC(12, 2)` / `NUMERIC(14, 2)` with zero floating-point math.
14. **Payment Idempotency**: Unique `PayPal-Request-Id` headers passed in provider calls to eliminate duplicate transactions.
15. **Authoritative Payment Settlement**: Client redirects to `/payments/success` are untrusted; only server-to-server captures or cryptographically verified webhooks can settle funds.
16. **Remote PayPal Webhook Verification**: Verifies transmission headers against PayPal’s verification API.
17. **Webhook Replay Protection**: Database unique constraint on `webhook_events.provider_event_id` prevents duplicate webhook execution.
18. **AI Quote Sandboxing**: Invariant checks confirm the recommended quote ID exists in the database; model cannot invent suppliers or prices.
19. **Safe Model Serialization**: Model artifacts serialized via plain JSON rather than insecure Python `pickle` objects.
20. **Strict CORS Whitelisting**: Explicitly configured origins (`localhost:3000`, `localhost:5173`, `aeon-control.vercel.app`); disallows wildcard `*` with credentials.
21. **Correlation ID Tracking**: `CorrelationIdMiddleware` injects `X-Correlation-ID` across all request/response cycles for audit tracing.
22. **Append-Only Audit Logging**: Dedicated `audit_events` table recording every administrative, policy, agent, and settlement action.

---

## 4. Latent Vulnerabilities, Blindspots & Hardening Needs

Despite the strong baseline, the deep code audit uncovered significant risks that require enterprise-grade remediation:

### Critical Security Vulnerabilities
- **Webhook Verification Bypass Backdoor**: In `app/integrations/paypal/webhook_verifier.py`, the header check `if h.get("x-mock-webhook") == "true": return True` is unconditioned on `APP_ENV == "testing"`. In production, an attacker sending this header can forge payment completion webhooks without paying.
- **Approval Expiration Budget Deadlock**: In `app/services/approval_service.py` (`list_approvals`), expired approvals are transitioned to `EXPIRED`, but the underlying `PurchaseRequest` remains `REQUIRES_APPROVAL` and the `BudgetReservation` is never released. Once marked `EXPIRED`, the approval cannot be decided, locking corporate budget in limbo forever.
- **Insecure Default Secret Key**: In `app/core/config.py`, `SECRET_KEY` defaults to a known insecure placeholder. If deployed without setting this secret, any attacker can forge administrative JWT tokens.

### Enterprise Security Blindspots
- **Lack of Rate Limiting / DoS Defense**: No rate limiting or burst throttling exists across login or purchase submission endpoints. Autonomous agents in infinite loops could starve connection pools.
- **Missing Administrative MFA / Step-Up Auth**: Financial platforms require Multi-Factor Authentication (TOTP / WebAuthn) for high-value approvals or administrative policy modifications.
- **No Token Revocation / Refresh Token Rotation**: JWT access tokens are valid for 60 minutes with no refresh token mechanism, no revocation table, and no session monitoring.
- **Unprotected Audit Ledger**: The audit trail is stored in standard relational rows without cryptographic hash-chaining (Merkle tree / blockchain-style chaining), leaving it vulnerable to silent tampering if database credentials are breached.
- **Lack of Agent Kill-Switch & Anomaly Detection**: No circuit breaker exists to instantly freeze a compromised or runaway autonomous agent across all endpoints.
- **Unvalidated Outbound Calls (SSRF Risk)**: No outbound URL sanitization for webhooks or external integrations to block access to internal metadata services (`169.254.169.254`, `localhost`).

---

## 5. Non-Disruptive Enterprise Hardening Plan

To resolve these vulnerabilities without modifying existing contracts or disrupting production:

1. **`security_hardening/` Dedicated Architecture**:
   - All new cryptographic engines, MFA modules, rate limiters, security headers, fraud detection heuristics, and tamper-evident audit chainers will be authored in `security_hardening/`.
2. **Safe Integration via Non-Blocking Middleware**:
   - Register a unified `SecurityHardeningMiddleware` and non-disruptive security router mount into FastAPI without altering existing schemas or route handlers.
3. **Safe Patch for Critical Bugs**:
   - Condition the mock webhook bypass strictly to non-production/test environments.
   - Fix the budget release leak when an approval expires.
4. **Comprehensive Automated Test Suite**:
   - Implement rigorous security test suites under `security_hardening/tests/` to guarantee zero regressions across the existing 110 tests while validating all new security layers.

