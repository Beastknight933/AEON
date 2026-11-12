# AEON — Enterprise Deployment Prerequisites & Configuration Runbook

**Date**: November 2026  
**Document Status**: Final  
**Scope**: Staging & Production Deployment Operational Requirements  

---

## 1. Overview & Phased Rollout Philosophy

To guarantee zero downtime and prevent production disruptions, enterprise security hardening features are designed to be deployed in three progressive phases:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                       ENTERPRISE ROLLOUT PHASES                             │
├───────────────────┬───────────────────────────────────┬─────────────────────┤
│ Phase             │ Operating Mode                    │ Purpose             │
├───────────────────┼───────────────────────────────────┼─────────────────────┤
│ Phase 1: Inactive │ Deploy code with SECURITY_ENABLED │ Verify startup and  │
│                   │ = True, ENFORCEMENT_MODE = False  │ backward-compat     │
├───────────────────┼───────────────────────────────────┼─────────────────────┤
│ Phase 2: Advisory │ ENFORCEMENT_MODE = False          │ Monitor logs and    │
│                   │ (Log & alert on anomalies)        │ verify thresholds   │
├───────────────────┼───────────────────────────────────┼─────────────────────┤
│ Phase 3: Active   │ ENFORCEMENT_MODE = True           │ Full blocking and   │
│                   │ (Block attacks, enforce limits)   │ hard enforcement    │
└───────────────────┴───────────────────────────────────┴─────────────────────┘
```

---

## 2. Environment Variables Specification

All security settings are configured using the `SECURITY_` environment variable prefix. If any variable is omitted, a safe, production-grade default is automatically applied.

| Environment Variable | Type | Default Value | Description |
| :--- | :--- | :--- | :--- |
| `SECURITY_ENABLED` | Boolean | `true` | Master feature toggle for the entire security hardening module. |
| `SECURITY_ENFORCEMENT_MODE`| Boolean | `true` | When `true`, violations result in HTTP 4xx errors. When `false`, violations are logged as advisory alerts without blocking. |
| `SECURITY_MASTER_KEY` | String (Hex) | *(Ephemeral Dev Key)* | 64-character hex string representing a 256-bit AES master key used for envelope encryption of sensitive credentials. In production, this must be provisioned via KMS or secret manager. |
| `SECURITY_MAX_REQUEST_BODY_BYTES` | Integer | `1048576` (1 MB) | Maximum permitted HTTP request body size to guard against payload flooding DoS. |
| `SECURITY_REQUEST_TIMEOUT_SECONDS` | Float | `30.0` | Maximum request execution window before ASGI timeout. |
| `SECURITY_RATE_LIMIT_ENABLED` | Boolean | `true` | Enables token-bucket rate limiting for IP addresses, agents, and organizations. |
| `SECURITY_RATE_LIMIT_GLOBAL_RPS` | Integer | `100` | Global platform-wide request-per-second ceiling. |
| `SECURITY_RATE_LIMIT_PER_IP_BURST`| Integer | `60` | Maximum burst capacity per client IP address. |
| `SECURITY_RATE_LIMIT_PER_IP_REPLENISH`| Float | `10.0` | Replenishment rate (tokens per second) per IP address. |
| `SECURITY_AUTH_ATTEMPTS_MAX_BURST`| Integer | `5` | Maximum failed authentication attempts before triggering brute-force IP lockout. |
| `SECURITY_AUTH_ATTEMPTS_LOCKOUT_SECONDS`| Integer | `300` (5 min) | Duration of IP lockout following repeated authentication failures. |
| `SECURITY_MFA_ENABLED` | Boolean | `true` | Enables RFC 6238 TOTP Multi-Factor Authentication endpoints. |
| `SECURITY_MFA_ISSUER_NAME` | String | `"AEON Control Plane"`| Label displayed in Google Authenticator / 1Password / Authy. |
| `SECURITY_STEP_UP_TIMEOUT_SECONDS`| Integer | `300` (5 min) | Lifetime of step-up authorization tokens for privileged administrative actions. |
| `SECURITY_REFRESH_TOKEN_EXPIRE_DAYS`| Integer | `7` | Maximum lifetime of rotating refresh token families. |
| `SECURITY_AGENT_KILL_SWITCH_ENABLED`| Boolean | `true` | Enables emergency kill switch controls (individual agent freeze and global purchasing freeze). |
| `SECURITY_PROMPT_INJECTION_SCAN_ENABLED`| Boolean | `true` | Enables recursive regex scanning for adversarial jailbreaks on procurement inputs. |
| `SECURITY_LEDGER_INTEGRITY_CHECK_ENABLED`| Boolean | `true` | Enforces double-entry balance conservation on financial transactions. |
| `SECURITY_DUPLICATE_TX_WINDOW_SECONDS`| Integer | `60` | Sliding window duration to detect and reject identical agent purchase requests. |
| `SECURITY_WEBHOOK_MAX_AGE_SECONDS`| Integer | `300` (5 min) | Maximum allowed age of incoming webhook timestamps to prevent replay attacks. |

---

## 3. Cryptographic Key Management (KMS / HSM) Setup

### 3.1. Development & Staging
In local or staging environments, a 256-bit AES key can be generated with OpenSSL:
```bash
openssl rand -hex 32
```
Set the output as the `SECURITY_MASTER_KEY` environment variable.

### 3.2. Production (AWS KMS / HashiCorp Vault / GCP KMS)
For enterprise production deployments (e.g. PayPal-grade assurance), do not store raw master keys in environment files. Instead, use a managed KMS adapter:

1. **AWS KMS**:
   - Create a symmetric KMS key: `aws kms create-key --description "AEON Master KEK"`.
   - Grant the AEON service IAM role permissions: `kms:GenerateDataKey`, `kms:Decrypt`.
   - Connect the KMS key ID to `KMSProvider` in `security_hardening/crypto/key_management.py`.

2. **HashiCorp Vault**:
   - Enable the Transit Secrets Engine: `vault secrets enable transit`.
   - Create a key: `vault write -f transit/keys/aeon-master`.
   - Configure Vault token and address in `KMSProvider`.

---

## 4. PostgreSQL Row-Level Security (RLS) Enablement

When approved by database administrators, execute the provided RLS policy script against the Supabase PostgreSQL database:

```sql
-- File: security_hardening/authorization/rls_policy.sql

-- 1. Enable RLS on core multi-tenant tables
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE users ENABLE ROW LEVEL SECURITY;
ALTER TABLE memberships ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE approval_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE ledger_entries ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_logs ENABLE ROW LEVEL SECURITY;

-- 2. Create Tenant Isolation Policy
CREATE POLICY tenant_isolation_policy ON purchase_requests
    FOR ALL
    USING (organization_id = NULLIF(current_setting('app.current_tenant_id', true), '')::uuid);
```

**Prerequisite Check**: Before running in production, verify that connection poolers (Supabase / PgBouncer) operate in `SESSION` mode or that the application sets tenant context inside an explicit transaction block via `SET LOCAL app.current_tenant_id = :org_id;`.

---

## 5. WebAuthn / Passkey Production Configuration

To enable WebAuthn passkeys in production:
1. Ensure the application is served over valid TLS/HTTPS.
2. Configure `WEBAUTHN_RP_ID` to match the exact top-level domain (e.g. `aeon-control.vercel.app`).
3. Set `WEBAUTHN_ORIGIN` to `https://aeon-control.vercel.app`.

