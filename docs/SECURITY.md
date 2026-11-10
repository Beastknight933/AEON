# AEON Security Model & Threat Mitigation

AEON employs defense-in-depth across dashboard users, autonomous agents, and third-party payment gateways.

---

## 1. Dual Independent Authentication Schemes

### Scheme A: Dashboard Administrators (Human)
- **Password Hashing**: Argon2id (`argon2-cffi`), memory-hard and GPU-resistant.
- **Session Tokens**: Short-lived signed JWT access tokens (`HS256`, 60 minutes default expiration).
- **Tenant Scope**: User membership in organizations is checked at the repository and service layer.
- **RBAC**: Three roles: `ADMIN`, `APPROVER`, `MEMBER`.

### Scheme B: Autonomous AI Agents (Machine-to-Machine)
- **Key Generation**: Cryptographically secure 256-bit random tokens prefixed with `aeon_live_`.
- **One-Time Exposure**: Raw key is returned **once** upon creation or rotation. It is never logged or returned again.
- **Storage**: Database stores only:
  - `key_prefix`: First 16 characters for fast, indexed candidate lookup.
  - `key_hash`: SHA-256 hash.
- **Verification**: Constant-time comparison (`hmac.compare_digest`) prevents timing side-channel attacks.
- **Zero-Trust Identity**: The backend **never** trusts `agent_id` or `organization_id` supplied in request bodies. Identity is resolved strictly from the verified credential.

---

## 2. Hard Policy Authorization Constraint

> **"A hard policy violation must never be overridden by a human approver."**

If a purchase request violates:
1. Agent active state,
2. Supplier allow-list,
3. Per-transaction limit,
4. Daily spending limit,
5. Currency support, or
6. Available budget,

the status is set to `BLOCKED`. Human approvals cannot override `BLOCKED` requests; the service will reject approval attempts with `PolicyViolationError`.

---

## 3. Financial Integrity & Idempotency

- **Row-Level Locking**: `SELECT ... FOR UPDATE` ensures no race conditions when multiple agents simultaneously attempt to reserve budget from the same pool.
- **Payment Idempotency**: Unique idempotency keys are passed in PayPal API calls (`PayPal-Request-Id`).
- **Webhook Signature Verification**: Webhooks verify PayPal transmission signatures and reject duplicates via `provider_event_id` uniqueness.
- **No Floating-Point Math**: Financial amounts use `Decimal` and PostgreSQL `NUMERIC(12, 2)` to eliminate floating-point precision leakage.

---

## 4. Network & CORS Policy

- CORS origins are explicitly whitelisted (e.g. `https://aeon-control.vercel.app`, `http://localhost:3000`).
- Wildcard `*` origins are strictly prohibited when credentials are allowed.
