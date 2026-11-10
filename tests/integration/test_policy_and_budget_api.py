import decimal
import uuid
import pytest


@pytest.mark.asyncio
async def test_policy_and_budget_full_api_workflow(async_client):
    # 1. Register admin and get token
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "cfo@enterprise.io",
            "password": "Password123!",
            "full_name": "Chief Financial Officer",
            "organization_name": "Enterprise Holdings",
        },
    )
    assert reg_res.status_code == 201
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Create Agent
    agent_res = await async_client.post(
        "/api/v1/agents",
        headers=headers,
        json={"name": "ProcurementAgent-42"},
    )
    assert agent_res.status_code == 201
    agent_id = agent_res.json()["agent"]["id"]

    # 3. Create Policy (Version 1)
    policy_res = await async_client.post(
        "/api/v1/policies",
        headers=headers,
        json={
            "name": "Cloud Spend Policy",
            "description": "Standard compute governance policy",
            "max_amount_per_transaction": "500.00",
            "max_amount_per_day": "1500.00",
            "approval_threshold_amount": "200.00",
            "allowed_suppliers": ["mock_supplier_a", "mock_supplier_b"],
            "allowed_currencies": ["USD"],
        },
    )
    assert policy_res.status_code == 201
    p_data = policy_res.json()
    policy_id = p_data["id"]
    assert p_data["current_version"] == 1
    assert len(p_data["versions"]) == 1

    # 4. Append immutable Policy Version 2
    v2_res = await async_client.post(
        f"/api/v1/policies/{policy_id}/versions",
        headers=headers,
        json={
            "max_amount_per_transaction": "800.00",
            "max_amount_per_day": "2500.00",
            "approval_threshold_amount": "250.00",
            "allowed_suppliers": ["mock_supplier_a", "mock_supplier_b"],
            "allowed_currencies": ["USD"],
        },
    )
    assert v2_res.status_code == 201
    assert v2_res.json()["version"] == 2

    # Check policy detail reflects current version 2
    get_p = await async_client.get(f"/api/v1/policies/{policy_id}", headers=headers)
    assert get_p.status_code == 200
    assert get_p.json()["current_version"] == 2
    assert len(get_p.json()["versions"]) == 2

    # 5. Assign policy to agent
    assign_res = await async_client.post(
        f"/api/v1/policies/assignments/{agent_id}",
        headers=headers,
        json={"policy_id": policy_id},
    )
    assert assign_res.status_code == 200
    assert assign_res.json()["is_active"] is True

    get_assign = await async_client.get(
        f"/api/v1/policies/assignments/{agent_id}",
        headers=headers,
    )
    assert get_assign.status_code == 200
    assert get_assign.json()["policy_id"] == policy_id

    # 6. Create Budget
    budget_res = await async_client.post(
        "/api/v1/budgets",
        headers=headers,
        json={
            "name": "Q4 Engineering Budget",
            "allocated_amount": "3000.00",
            "currency": "USD",
        },
    )
    assert budget_res.status_code == 201
    budget_data = budget_res.json()
    budget_id = budget_data["id"]
    assert budget_data["allocated_amount"] == "3000.00"
    assert budget_data["available_amount"] == "3000.00"

    # 7. Evaluate Policy API
    # 7a. Under approval threshold ($150 <= $250)
    eval_1 = await async_client.post(
        "/api/v1/policies/evaluate",
        headers=headers,
        json={
            "agent_id": agent_id,
            "amount": "150.00",
            "currency": "USD",
            "supplier_code": "mock_supplier_a",
        },
    )
    assert eval_1.status_code == 200
    d1 = eval_1.json()
    assert d1["allowed"] is True
    assert d1["requires_approval"] is False

    # 7b. Above approval threshold ($400 > $250)
    eval_2 = await async_client.post(
        "/api/v1/policies/evaluate",
        headers=headers,
        json={
            "agent_id": agent_id,
            "amount": "400.00",
            "currency": "USD",
            "supplier_code": "mock_supplier_a",
        },
    )
    assert eval_2.status_code == 200
    d2 = eval_2.json()
    assert d2["allowed"] is True
    assert d2["requires_approval"] is True

    # 7c. Hard Violation: Unallowed supplier
    eval_3 = await async_client.post(
        "/api/v1/policies/evaluate",
        headers=headers,
        json={
            "agent_id": agent_id,
            "amount": "100.00",
            "currency": "USD",
            "supplier_code": "unauthorized_store",
        },
    )
    assert eval_3.status_code == 200
    d3 = eval_3.json()
    assert d3["allowed"] is False
    assert "SUPPLIER_NOT_ALLOWED" in d3["reason_codes"]

    # 7d. Hard Violation: Exceeds per-transaction limit ($1000 > $800)
    eval_4 = await async_client.post(
        "/api/v1/policies/evaluate",
        headers=headers,
        json={
            "agent_id": agent_id,
            "amount": "1000.00",
            "currency": "USD",
            "supplier_code": "mock_supplier_a",
        },
    )
    assert eval_4.status_code == 200
    d4 = eval_4.json()
    assert d4["allowed"] is False
    assert "PER_TRANSACTION_LIMIT_EXCEEDED" in d4["reason_codes"]

    # 8. Budget Reservation Workflow via API
    # 8a. Reserve $500
    pr_uuid = str(uuid.uuid4())
    reserve_res = await async_client.post(
        f"/api/v1/budgets/{budget_id}/reserve",
        headers=headers,
        json={"purchase_request_id": pr_uuid, "amount": "500.00", "currency": "USD"},
    )
    assert reserve_res.status_code == 201
    res_data = reserve_res.json()
    res_id = res_data["id"]
    assert res_data["status"] == "ACTIVE"

    # Verify budget updated
    b_check = await async_client.get(f"/api/v1/budgets/{budget_id}", headers=headers)
    assert b_check.json()["reserved_amount"] == "500.00"
    assert b_check.json()["available_amount"] == "2500.00"

    # 8b. List reservations
    res_list = await async_client.get(f"/api/v1/budgets/{budget_id}/reservations", headers=headers)
    assert res_list.status_code == 200
    assert len(res_list.json()) == 1

    # 8c. Settle reservation
    settle_res = await async_client.post(
        f"/api/v1/budgets/reservations/{res_id}/settle",
        headers=headers,
    )
    assert settle_res.status_code == 200
    assert settle_res.json()["status"] == "SETTLED"

    b_after_settle = await async_client.get(f"/api/v1/budgets/{budget_id}", headers=headers)
    assert b_after_settle.json()["reserved_amount"] == "0.00"
    assert b_after_settle.json()["spent_amount"] == "500.00"
    assert b_after_settle.json()["available_amount"] == "2500.00"

    # 8d. Reserve $300 and release it
    res2 = await async_client.post(
        f"/api/v1/budgets/{budget_id}/reserve",
        headers=headers,
        json={"purchase_request_id": str(uuid.uuid4()), "amount": "300.00", "currency": "USD"},
    )
    res2_id = res2.json()["id"]

    release_res = await async_client.post(
        f"/api/v1/budgets/reservations/{res2_id}/release",
        headers=headers,
    )
    assert release_res.status_code == 200
    assert release_res.json()["status"] == "RELEASED"

    b_after_release = await async_client.get(f"/api/v1/budgets/{budget_id}", headers=headers)
    assert b_after_release.json()["reserved_amount"] == "0.00"
    assert b_after_release.json()["spent_amount"] == "500.00"
    assert b_after_release.json()["available_amount"] == "2500.00"
