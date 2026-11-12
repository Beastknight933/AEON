# AEON — Comprehensive Enterprise Regulatory & Security Compliance Matrix

**Date**: November 2026  
**Document Status**: Final  
**Frameworks Evaluated**:
1. **OWASP ASVS 5.0 Level 3** (Application Security Verification Standard)
2. **OWASP API Security Top 10 (2023)**
3. **PCI DSS v4.0.1** (Payment Card Industry Data Security Standard)
4. **GDPR / Indian DPDP Act 2023** (Data Privacy & Personal Data Protection)
5. **NIST CSF 2.0** (Cybersecurity Framework)

---

## 1. OWASP API Security Top 10 (2023) Compliance Mapping

| Threat / Standard | Requirement Summary | AEON Hardening Implementation | Source File | Status |
| :--- | :--- | :--- | :--- | :--- |
| **API1:2023 Broken Object Level Authorization (BOLA)** | Prevent unauthorized access to objects belonging to other tenants. | `ObjectLevelAuthorizer` checks entity ownership on every query and mutation. PostgreSQL RLS policies enforce DB isolation. | `security_hardening/authorization/object_level.py` | **COMPLIANT** |
| **API2:2023 Broken Authentication** | Protect against credential stuffing, weak token handling, and session fixation. | Argon2id password hashing, RFC 6238 TOTP MFA, Refresh Token Family Rotation with reuse detection, and IP lockout. | `security_hardening/authentication/mfa.py`, `tokens.py` | **COMPLIANT** |
| **API3:2023 Broken Object Property Level Authorization** | Guard against mass assignment and unauthorized property exposure. | Input validator strips unexpected attributes; Pydantic strict schemas; `SensitiveDataRedactor` masks secrets. | `security_hardening/api_protection/input_validation.py` | **COMPLIANT** |
| **API4:2023 Unrestricted Resource Consumption** | Prevent DoS via unbounded request payload or rate exhaustion. | 1MB payload ceiling, request execution timeout (30s), Token-Bucket rate limiting by IP, agent, and org. | `security_hardening/api_protection/rate_limiter.py`, `request_limits.py` | **COMPLIANT** |
| **API5:2023 Broken Function Level Authorization (BFLA)** | Ensure administrative endpoints require verified privileges. | RBAC (`ADMIN`, `APPROVER`, `MEMBER`), Agent Scopes (`procurement:create`), and Step-Up tokens for sensitive actions. | `security_hardening/authorization/agent_scopes.py`, `step_up.py` | **COMPLIANT** |
| **API6:2023 Unrestricted Access to Sensitive Business Flows** | Guard high-value transactions against automation abuse. | Deterministic hard policy engine, agent velocity tracking, sliding-window duplicate detector, and kill switch. | `security_hardening/agent_security/kill_switch.py`, `duplicate_detector.py` | **COMPLIANT** |
| **API7:2023 Server Side Request Forgery (SSRF)** | Restrict outbound HTTP connections to safe external endpoints. | `SSRFProtector` blocks loopback, private RFC 1918 subnets, and cloud metadata (`169.254.169.254`). | `security_hardening/api_protection/ssrf_protection.py` | **COMPLIANT** |
| **API8:2023 Security Misconfiguration** | Enforce security headers, CORS restrictions, and safe error messages. | HSTS (`max-age=31536000`), CSP, `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`, sanitization of error traces. | `security_hardening/network_security/headers.py` | **COMPLIANT** |
| **API9:2023 Improper Inventory Management** | Monitor API versions, deprecation, and authorized endpoints. | Clean `/api/v1/` versioning, centralized router registration, OpenAPI schema isolation. | `security_hardening/integrations/routes.py` | **COMPLIANT** |
| **API10:2023 Unsafe Consumption of APIs** | Validate and sanitize incoming third-party webhooks and payloads. | PayPal webhook signature verification, timestamp replay check (300s window), and isolated dead-letter quarantine. | `security_hardening/integrations/webhook_guard.py` | **COMPLIANT** |

---

## 2. OWASP ASVS 5.0 Level 3 (Selected High-Assurance Controls)

| ASVS Section | Control ID | Requirement | AEON Hardening Implementation | Verification |
| :--- | :--- | :--- | :--- | :--- |
| **V1 Architecture** | V1.1.1 | Verify defense-in-depth architecture. | 14 isolated subsystems covering ingress, application, database, and integrations. | Pass (Architecture Review) |
| **V2 Authentication** | V2.1.1 | Verify password complexity and hashing. | Argon2id hashing with salt and memory cost configuration. | Pass (`tests/unit/test_auth.py`) |
| **V2 Authentication** | V2.8.1 | Verify multi-factor authentication (MFA). | RFC 6238 TOTP + 8 single-use backup recovery codes. | Pass (`test_authentication_and_session.py`) |
| **V3 Session Management**| V3.2.1 | Verify token expiration and revocation. | Short-lived JWTs (60m), Refresh token family rotation with reuse detection, and session revocation registry. | Pass (`test_authentication_and_session.py`) |
| **V4 Access Control** | V4.1.1 | Enforce least privilege and RBAC. | Role-based authorization (`require_roles`), granular agent capability scopes. | Pass (`test_live_security_endpoints.py`) |
| **V5 Cryptography** | V5.1.1 | Use approved modern cryptographic algorithms. | AES-256-GCM envelope encryption, SHA-256 HMAC, constant-time comparisons. | Pass (`test_cryptography_and_envelope.py`) |
| **V7 Error Handling** | V7.1.1 | Prevent sensitive data leakage in logs. | `SensitiveDataRedactor` automatically filters secrets, tokens, card numbers, and passwords. | Pass (`test_financial_and_audit_security.py`) |
| **V8 Data Protection** | V8.2.1 | Protect data in transit and at rest. | Forced TLS / HSTS preload, AES-256-GCM encrypted database columns. | Pass (`test_cryptography_and_envelope.py`) |
| **V10 Malicious Code** | V10.3.1 | Prevent AI prompt injection and jailbreaks. | `PromptInjectionGuard` scans all procurement requirement payloads before ML processing. | Pass (`test_agent_and_prompt_security.py`) |
| **V11 Business Logic** | V11.1.1 | Enforce transaction state machine and double-entry invariants. | Strict DAG state transitions (`PENDING` -> `APPROVED` -> `COMPLETED`) + conservation equation verifier. | Pass (`test_financial_and_audit_security.py`) |

---

## 3. PCI DSS v4.0.1 Compliance Mapping

| PCI DSS Requirement | Standard Mandate | AEON Hardening Control | Verification Status |
| :--- | :--- | :--- | :--- |
| **Req 3: Protect Stored Account Data** | Never store raw PAN or CVV; encrypt cardholder data with strong cryptography. | AEON delegates raw card processing to PayPal (PCI DSS Level 1 Provider); all local credentials encrypted with AES-256-GCM envelope encryption. | **COMPLIANT** |
| **Req 6: Develop Secure Systems** | Protect web applications against common attacks (SQLi, XSS, SSRF, DoS). | SQL query guards, parameterized SQLAlchemy ORM, SSRF protector, and 1MB request limits. | **COMPLIANT** |
| **Req 8: Identify Users & Authenticate Access**| Require strong multi-factor authentication for administrative access. | RFC 6238 TOTP MFA + WebAuthn passkey infrastructure for administrators. | **COMPLIANT** |
| **Req 10: Log & Monitor All Access** | Maintain tamper-evident, append-only audit trails for financial actions. | Cryptographic SHA-256 hash chaining links all audit log records sequentially. | **COMPLIANT** |
| **Req 11: Test Security Regularly** | Automated vulnerability testing and regression verification. | 143 automated test suites executed on every code iteration. | **COMPLIANT** |

---

## 4. Privacy Regulations: GDPR & Indian DPDP Act 2023

| Privacy Principle | Regulatory Mandate | AEON Hardening Implementation | Status |
| :--- | :--- | :--- | :--- |
| **Data Minimization (Art. 5 GDPR / Sec. 6 DPDP)** | Collect only data necessary for procurement operations. | Purchase requests store only item metadata and estimated amounts; no personal end-user browsing data stored. | **COMPLIANT** |
| **Integrity & Confidentiality (Art. 32 GDPR)** | Implement appropriate technical security measures. | AES-256-GCM envelope encryption, Argon2id, and HTTPS/HSTS enforcement. | **COMPLIANT** |
| **Right to Erasure / Redaction** | Enable secure deletion and masking of personal identifiers. | Tenant isolation guarantees; `SensitiveDataRedactor` removes credentials from operational logs. | **COMPLIANT** |
| **Accountability & Auditability (Sec. 8 DPDP)**| Demonstrate compliance through verifiable audit records. | Tamper-evident hash chaining ensures non-repudiation of financial approvals. | **COMPLIANT** |

---

## 5. NIST Cybersecurity Framework (CSF) 2.0 Mapping

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          NIST CSF 2.0 MAPPING                               │
├───────────────┬───────────────────────────────────┬─────────────────────────┤
│ Function      │ Implementation Category           │ AEON Subsystem          │
├───────────────┼───────────────────────────────────┼─────────────────────────┤
│ GOVERN (GV)   │ Hard Spending Policies & RBAC     │ Policy Engine & Scopes  │
│ IDENTIFY (ID) │ Multi-Tenant Inventory & IAM      │ Agent & User Management │
│ PROTECT (PR)  │ AES-256-GCM, MFA, SSRF, HSTS      │ Crypto, Auth, API Guard │
│ DETECT (DE)   │ Fraud Scoring, Prompt Injection   │ Prompt Guard & Engine   │
│ RESPOND (RS)  │ Granular & Global Kill Switch     │ Agent Kill Switch       │
│ RECOVER (RC)  │ Backup Codes, Token Revocation    │ Session & MFA Recovery  │
└───────────────┴───────────────────────────────────┴─────────────────────────┘
```

