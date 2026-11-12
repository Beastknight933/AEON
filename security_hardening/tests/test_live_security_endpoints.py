"""Integration Tests for Security Hardening Endpoints and Middleware Headers."""

import pytest


async def setup_security_test_org(async_client, org_name="SecCorp", admin_email="admin@seccorp.io"):
    # 1. Register Admin
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": admin_email,
            "password": "SecurePassword123!",
            "full_name": "Security Administrator",
            "organization_name": org_name,
        },
    )
    assert reg_res.status_code == 201, reg_res.text
    token = reg_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {token}"}

    # 2. Get Organization ID
    me_res = await async_client.get("/api/v1/auth/me", headers=admin_headers)
    assert me_res.status_code == 200
    org_id = me_res.json()["organization"]["id"]

    # 3. Create Agent
    agent_res = await async_client.post(
        "/api/v1/agents",
        headers=admin_headers,
        json={"name": "SecBot-1", "description": "Security test bot"},
    )
    assert agent_res.status_code == 201, agent_res.text
    agent_data = agent_res.json()
    agent_id = agent_data["agent"]["id"]
    api_key = agent_data["credentials"]["raw_api_key"]
    agent_headers = {"X-Agent-API-Key": api_key}

    # 4. Create Policy
    pol_res = await async_client.post(
        "/api/v1/policies",
        headers=admin_headers,
        json={
            "name": "Sec Policy",
            "max_amount_per_transaction": "1000.00",
            "max_amount_per_day": "5000.00",
            "approval_threshold_amount": "500.00",
            "allowed_suppliers": ["mock_supplier_a", "mock_supplier_b"],
            "allowed_currencies": ["USD"],
        },
    )
    assert pol_res.status_code == 201
    pol_id = pol_res.json()["id"]

    # 5. Assign policy to agent
    await async_client.post(
        f"/api/v1/policies/assignments/{agent_id}",
        headers=admin_headers,
        json={"policy_id": pol_id},
    )

    # 6. Create Budget
    await async_client.post(
        "/api/v1/budgets",
        headers=admin_headers,
        json={"name": "Sec Budget", "allocated_amount": "10000.00", "currency": "USD"},
    )

    return {
        "admin_headers": admin_headers,
        "agent_headers": agent_headers,
        "agent_id": agent_id,
        "org_id": org_id,
    }


@pytest.mark.asyncio
async def test_enterprise_security_response_headers(async_client):
    """Verify that all HTTP responses carry enterprise-grade security headers."""
    res = await async_client.get("/health")
    assert res.status_code == 200
    headers = res.headers

    assert headers.get("x-frame-options") == "DENY"
    assert headers.get("x-content-type-options") == "nosniff"
    assert "strict-transport-security" in headers
    assert "content-security-policy" in headers
    assert "permissions-policy" in headers
    assert "x-response-time" in headers


@pytest.mark.asyncio
async def test_mfa_endpoints_workflow(async_client):
    """Test MFA setup and code verification via live API."""
    ctx = await setup_security_test_org(async_client, org_name="MFA-Corp", admin_email="mfa-admin@corp.io")

    # 1. Setup MFA
    setup_res = await async_client.post("/api/v1/security/mfa/setup", headers=ctx["admin_headers"])
    assert setup_res.status_code == 200
    data = setup_res.json()
    assert "secret" in data
    assert "provisioning_uri" in data
    assert len(data["recovery_codes"]) == 10

    secret = data["secret"]

    # 2. Verify invalid code
    bad_verify = await async_client.post(
        "/api/v1/security/mfa/verify",
        headers=ctx["admin_headers"],
        json={"secret": secret, "code": "000000"},
    )
    assert bad_verify.status_code == 400

    # 3. Verify valid code using TOTP engine
    from security_hardening.authentication.mfa import totp_engine
    valid_code = totp_engine.generate_code(secret)
    good_verify = await async_client.post(
        "/api/v1/security/mfa/verify",
        headers=ctx["admin_headers"],
        json={"secret": secret, "code": valid_code},
    )
    assert good_verify.status_code == 200
    assert good_verify.json()["verified"] is True


@pytest.mark.asyncio
async def test_kill_switch_endpoints(async_client):
    """Test agent freeze, status check, and unfreeze via security API."""
    ctx = await setup_security_test_org(async_client, org_name="KillSwitchCorp", admin_email="sec-ciso@corp.io")

    # 1. Check status
    status_res = await async_client.get("/api/v1/security/kill-switch/status", headers=ctx["admin_headers"])
    assert status_res.status_code == 200
    assert "global_freeze" in status_res.json()

    # 2. Freeze an agent
    agent_id = ctx["agent_id"]
    freeze_res = await async_client.post(
        "/api/v1/security/kill-switch/freeze-agent",
        headers=ctx["admin_headers"],
        json={"agent_id": agent_id, "reason": "Suspicious velocity detected"},
    )
    assert freeze_res.status_code == 200
    assert freeze_res.json()["status"] == "frozen"

    # 3. Attempt purchase with frozen agent -> 403 Forbidden with AGENT_KILL_SWITCH_ACTIVE
    purchase_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Server hardware",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert purchase_res.status_code == 403
    assert purchase_res.json()["error"]["code"] == "AGENT_KILL_SWITCH_ACTIVE"

    # 4. Unfreeze agent
    unfreeze_res = await async_client.post(
        f"/api/v1/security/kill-switch/unfreeze-agent?agent_id={agent_id}",
        headers=ctx["admin_headers"],
    )
    assert unfreeze_res.status_code == 200
    assert unfreeze_res.json()["status"] == "restored"


@pytest.mark.asyncio
async def test_audit_hash_chain_endpoint(async_client):
    """Test cryptographic audit chain verification endpoint."""
    ctx = await setup_security_test_org(async_client, org_name="AuditCorp", admin_email="auditor@corp.io")

    res = await async_client.get("/api/v1/security/audit/verify-chain", headers=ctx["admin_headers"])
    assert res.status_code == 200
    data = res.json()
    assert data["is_valid"] is True
    assert "total_blocks_verified" in data


@pytest.mark.asyncio
async def test_security_events_and_dead_letter_endpoints(async_client):
    """Test security monitoring event feed and dead-letter quarantine endpoints."""
    ctx = await setup_security_test_org(async_client, org_name="EventsCorp", admin_email="soc@corp.io")

    # List events
    events_res = await async_client.get("/api/v1/security/events", headers=ctx["admin_headers"])
    assert events_res.status_code == 200
    assert isinstance(events_res.json(), list)

    # List dead letters
    dl_res = await async_client.get("/api/v1/security/dead-letters", headers=ctx["admin_headers"])
    assert dl_res.status_code == 200
    assert isinstance(dl_res.json(), list)
