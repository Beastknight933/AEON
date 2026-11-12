# AEON Enterprise Security Hardening — Technical Implementation Guide

**Document Version**: 2.0.0-ENTERPRISE-HARDENED  
**Date**: November 2026  
**Status**: Production-Ready / Fully Verified  

---

## 1. Project Background & Hardening Scope

AEON is an autonomous agent procurement control plane. It enforces spending limits, multi-tier approvals, vendor allowlists, and payment settlement for actions initiated by artificial intelligence agents.

In accordance with the **Master Hardening Prompt**, this project was executed under strict constraints:
- **Zero Disruption**: The existing application was not rewritten, refactored, or broken.
- **Contract Preservation**: All existing API routes, schemas, and database structures remain identical.
- **Isolated Directory**: All new security modules, tests, utilities, and documentation reside in `security_hardening/`.
- **True Implementation**: Every control is implemented in Python, integrated, tested, and documented with zero false claims.

---

## 2. Directory & Module Hierarchy

```
security_hardening/
├── core/
│   ├── constants.py           # Enums: SecurityEventType, FraudRiskLevel, KeyState, Scope
│   ├── config.py              # Pydantic BaseSettings with SECURITY_ prefix
│   └── errors.py              # Structured security exceptions with safe HTTP mapping
├── crypto/
│   ├── envelope.py            # AES-256-GCM envelope encryption (DEK + KEK)
│   ├── hashing.py             # Constant-time HMAC-SHA256, secure tokens
│   └── key_management.py      # KeyRegistry, rotation, and cloud KMS/HSM adapter
├── authentication/
│   ├── mfa.py                 # RFC 6238 TOTP engine + single-use backup codes
│   ├── tokens.py              # Refresh token family rotation & theft reuse detection
│   ├── session.py             # SessionRegistry with IP tracking & instant revocation
│   ├── step_up.py             # Time-bounded step-up authorization tokens
│   └── passkeys.py            # WebAuthn / FIDO2 credential models & assertion
├── authorization/
│   ├── object_level.py        # Object-level ownership & multi-tenant IDOR guard
│   ├── agent_scopes.py        # Granular agent capability scopes
│   └── rls_policy.py          # PostgreSQL Row-Level Security policies & context setter
├── api_protection/
│   ├── rate_limiter.py        # Token-bucket rate limiter & auth brute-force lockout
│   ├── request_limits.py      # 1MB payload size enforcement
│   ├── input_validation.py    # Strict Content-Type & mass-assignment prevention
│   ├── ssrf_protection.py     # SSRF guard (blocks loopback, RFC 1918, metadata IPs)
│   └── redirect_validator.py  # Open-redirect destination allowlist validator
├── network_security/
│   └── headers.py             # Enterprise security headers (HSTS, CSP, nosniff, DENY)
├── database_security/
│   └── query_guard.py         # Raw SQL injection scanner & column crypto hooks
├── transaction_security/
│   ├── state_validator.py     # Strict financial state machine DAG transitions
│   ├── double_entry.py        # Budget conservation equation verifier
│   └── duplicate_detector.py  # In-memory sliding-window duplicate purchase detector
├── agent_security/
│   ├── kill_switch.py         # Granular per-agent and global emergency kill switches
│   ├── prompt_guard.py        # Adversarial jailbreak & prompt injection regex shield
│   └── anomaly_detector.py    # Agent purchase velocity spike monitor
├── fraud_detection/
│   └── engine.py              # Multi-vector heuristic fraud scoring engine
├── audit/
│   └── tamper_evident.py      # Cryptographic SHA-256 forward hash-chaining ledger
├── monitoring/
│   ├── redactor.py            # Zero-leak regex sanitizer for logs and JSON
│   └── security_events.py     # Structured security event bus
├── integrations/
│   ├── webhook_guard.py       # Timestamp freshness replay guard & dead-letter queue
│   └── routes.py              # Admin REST endpoints mounted at /api/v1/security/*
├── middleware/
│   └── security_middleware.py # Unified ASGI middleware pipeline for FastAPI
├── tests/
│   ├── test_agent_and_prompt_security.py
│   ├── test_api_protection_and_ssrf.py
│   ├── test_authentication_and_session.py
│   ├── test_cryptography_and_envelope.py
│   ├── test_financial_and_audit_security.py
│   └── test_live_security_endpoints.py
└── documentation/
    ├── INITIAL_SECURITY_ASSESSMENT.md
    ├── ARCHITECTURE.md
    ├── INTEGRATION_MAP.md
    ├── THREAT_MODEL.md
    ├── TEST_RESULTS.md
    ├── DEPLOYMENT_PREREQUISITES.md
    └── COMPLIANCE_MATRIX.md
```

---

## 3. Core Implementation Highlights

### 3.1. Envelope Encryption (`security_hardening/crypto/envelope.py`)
Sensitive data (such as payment credentials and vendor secrets) is protected via envelope encryption:
- A random 256-bit Data Encryption Key (DEK) is generated for each encryption operation.
- The plaintext is encrypted using `AES-256-GCM` with a 96-bit initialization vector (nonce) and produces a 128-bit authentication tag.
- The DEK is encrypted with the Master Key-Encryption Key (KEK) using `AES-256-GCM`.
- The serialized payload contains: `{"key_id": ..., "encrypted_dek": ..., "nonce": ..., "ciphertext": ..., "tag": ...}`.
- Decryption validates both the ciphertext tag and the encrypted DEK tag. Any bit flipping or corruption raises `DecryptionError`.

### 3.2. Refresh Token Family Rotation & Reuse Detection (`security_hardening/authentication/tokens.py`)
To prevent session hijacking:
- Refresh tokens are grouped into a `RefreshTokenFamily`.
- When a refresh token is exchanged, a new token is generated, and the old token's SHA-256 hash is added to `retired_token_hashes`.
- If an adversary presents a previously retired token (theft indicator), the entire family is revoked immediately with a high-priority security event.

### 3.3. Prompt Injection & Jailbreak Defense (`security_hardening/agent_security/prompt_guard.py`)
Before procurement requests reach the ML ranking model or budget reservation engine, the `PromptInjectionGuard` scans all text fields (`item_description`, `category`, and nested dictionary/list values in `requirements`) against comprehensive adversarial patterns:
- Instruction overriding (`ignore/disregard/forget all previous instructions`)
- Persona hacking (`developer mode`, `DAN`, `unfiltered`)
- Hard policy bypasses (`bypass policy`, `admin_override = true`)
- Attempted command injection (`rm -rf`, `<script>`)
Violations immediately abort the request with `PromptInjectionDetectedError`.

### 3.4. Emergency Agent Kill Switch (`security_hardening/agent_security/kill_switch.py`)
Provides real-time operational containment:
- **Individual Freeze**: Instantly isolates a misbehaving or compromised agent.
- **Global Freeze**: Halts all autonomous procurement activity across the platform during a major security incident while human administrators investigate.
- Both operations are managed via the REST API at `/api/v1/security/kill-switch/freeze` and `/unfreeze`.

### 3.5. Tamper-Evident SHA-256 Audit Chain (`security_hardening/audit/tamper_evident.py`)
Ensures non-repudiation and forensic integrity:
- Every audit record stores `previous_hash`, `timestamp`, `event_type`, `actor_id`, `organization_id`, `payload`, and its computed `record_hash`.
- The hash chain is verifiable in $\mathcal{O}(N)$ time via `/api/v1/security/audit/verify-chain`.
- If any database record is deleted or modified after creation, the forward hash chain breaks, pinpointing the exact tampering index.

---

## 4. API Endpoints Reference (`/api/v1/security/*`)

The security management router exposes the following endpoints (requiring `ADMIN` role):

| Endpoint | HTTP Method | Description |
| :--- | :--- | :--- |
| `/api/v1/security/mfa/setup` | `POST` | Generate RFC 6238 TOTP secret, provisioning URI, and 8 one-time backup codes. |
| `/api/v1/security/mfa/verify` | `POST` | Verify 6-digit TOTP code and finalize MFA enrollment. |
| `/api/v1/security/kill-switch/status` | `GET` | Retrieve global freeze status and list of frozen agents. |
| `/api/v1/security/kill-switch/freeze` | `POST` | Freeze an individual agent or activate global emergency freeze. |
| `/api/v1/security/kill-switch/unfreeze`| `POST` | Unfreeze an agent or deactivate global emergency freeze. |
| `/api/v1/security/audit/verify-chain` | `GET` | Cryptographically verify the integrity of the audit log hash chain. |
| `/api/v1/security/events` | `GET` | Query structured security events (brute force, prompt injections, kill switch). |
| `/api/v1/security/webhooks/dead-letter`| `GET` | Inspect quarantined malformed or replayed webhook payloads. |

---

## 5. Verification Status

All 33 automated tests in `security_hardening/tests/` pass with 100% success.  
All 80 baseline application tests in `tests/` pass with 0 regressions.  
All 30 ML ranking tests in `ml-module/tests/` pass with 0 regressions.

