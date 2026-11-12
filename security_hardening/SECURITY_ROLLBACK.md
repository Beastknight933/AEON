# AEON — Enterprise Security Rollback & Disaster Recovery Runbook

**Document Status**: Final  
**Date**: November 2026  
**Target Invariant**: Production Availability Guarantee  

---

## 1. Overview & Rollback Guarantees

Because all security hardening components adhere to **Rule 1 (Preserve the existing application)** and **Rule 4 (Backward compatibility)**:
1. **No Database Migrations Were Forced**: No columns or tables were altered in existing production schemas.
2. **Instant Feature Toggles**: Any or all security controls can be disabled via environment variables without code modification.
3. **Decoupled Architecture**: Deleting or unmounting `security_hardening/` immediately restores the codebase to its exact pre-hardening state.

---

## 2. Option A: Zero-Downtime Instant Rollback (Recommended)

If an issue is detected in production (e.g., an unexpected rate limit trigger or false positive in prompt scanning), you can disable the controls immediately via Render environment variables without redeploying code.

### Step 1: Switch to Advisory Mode (Logging Only)
To stop blocking requests while retaining observability and audit logs:
```env
SECURITY_ENFORCEMENT_MODE=false
```
*Effect*: All requests that would have been blocked (rate limits, prompt injection, duplicate requests) are permitted to execute normally while generating warning logs.

### Step 2: Complete Feature Deactivation
To completely bypass all security hardening middleware, rate limits, and hooks:
```env
SECURITY_ENABLED=false
```
*Effect*: The `SecurityHardeningMiddleware` passes all requests directly to the underlying FastAPI application without inspection or header modification.

---

## 3. Option B: Code-Level Clean Rollback

If you wish to cleanly revert code modifications back to the exact initial baseline:

### Step 1: Remove Integration Hooks in `app/main.py`
In `app/main.py`, remove or comment out:
```python
# Remove these lines:
try:
    from security_hardening.middleware import SecurityHardeningMiddleware
    from security_hardening.integrations.routes import security_router
    app.add_middleware(SecurityHardeningMiddleware)
    app.include_router(security_router, prefix="/api/v1")
except ImportError:
    pass
```

### Step 2: Remove Domain Service Hooks in `app/services/procurement_service.py`
In `app/services/procurement_service.py`, remove:
```python
# Remove prompt injection, kill switch, and audit chain hooks:
try:
    from security_hardening.agent_security.kill_switch import agent_kill_switch
    from security_hardening.agent_security.prompt_guard import PromptInjectionGuard
    from security_hardening.audit.tamper_evident import audit_chain

    agent_kill_switch.assert_agent_active(str(agent.id))
    PromptInjectionGuard.sanitize_procurement_inputs(...)
    audit_chain.append_event(...)
except ImportError:
    pass
```

### Step 3: Remove `security_hardening/` Directory
Optionally delete or archive the `security_hardening/` folder:
```bash
rm -rf security_hardening/
```

---

## 4. Post-Rollback Verification Checklist

After executing a rollback:
- [ ] Run baseline test suite: `pytest tests/` (verify 80 passed).
- [ ] Run ML test suite: `pytest ml-module/tests/` (verify 30 passed).
- [ ] Verify HTTP health endpoint: `GET https://aeon-m136.onrender.com/health` returns HTTP 200 `{"status": "healthy"}`.
- [ ] Verify Supabase database readiness: `GET https://aeon-m136.onrender.com/ready` returns HTTP 200 `{"status": "ready", "database": "connected"}`.
- [ ] Verify frontend login: `https://aeon-control.vercel.app/login` loads correctly.

