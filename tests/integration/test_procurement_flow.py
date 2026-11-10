import decimal
import pytest
from app.core.constants import PurchaseStatus, ApprovalStatus, ReservationStatus
from app.models.approval import Approval
from sqlalchemy import select


@pytest.mark.asyncio
async def test_full_autonomous_procurement_authorized_directly(async_client):
    # 1. Register Admin User
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "ops@agentic.ai",
            "password": "SecurePassword123!",
            "full_name": "Ops Lead",
            "organization_name": "Agentic Labs",
        },
    )
    admin_token = reg_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Create Agent
    agent_res = await async_client.post(
        "/api/v1/agents",
        headers=admin_headers,
        json={"name": "ComputeProvisionerAgent"},
    )
    agent_data = agent_res.json()
    agent_id = agent_data["agent"]["id"]
    raw_key = agent_data["credentials"]["raw_api_key"]
    agent_headers = {"X-Agent-API-Key": raw_key}

    # 3. Create Budget ($10,000)
    budget_res = await async_client.post(
        "/api/v1/budgets",
        headers=admin_headers,
        json={
            "name": "Global Q4 Infrastructure Budget",
            "allocated_amount": "10000.00",
            "currency": "USD",
        },
    )
    assert budget_res.status_code == 201

    # 4. Create Policy: Max $500 per tx, Max $2000 per day, Approval threshold $200
    policy_res = await async_client.post(
        "/api/v1/policies",
        headers=admin_headers,
        json={
            "name": "Cloud Infrastructure Policy",
            "max_amount_per_transaction": "500.00",
            "max_amount_per_day": "2000.00",
            "approval_threshold_amount": "200.00",
            "allowed_suppliers": ["mock_supplier_a", "mock_supplier_b"],
            "allowed_currencies": ["USD"],
        },
    )
    assert policy_res.status_code == 201
    policy_id = policy_res.json()["id"]

    # 5. Assign policy to agent
    assign_res = await async_client.post(
        f"/api/v1/policies/assignments/{agent_id}",
        headers=admin_headers,
        json={"policy_id": policy_id},
    )
    assert assign_res.status_code == 200

    # 6. Agent submits small purchase ($120 < $200 threshold)
    purchase_res = await async_client.post(
        "/api/v1/purchases",
        headers=agent_headers,
        json={
            "item_description": "Standard compute worker node",
            "category": "compute",
            "max_budget": "150.00",
            "currency": "USD",
            "requirements": {"quantity": 1, "vcpus": 4},
        },
    )
    assert purchase_res.status_code == 201
    p_data = purchase_res.json()
    assert p_data["status"] == PurchaseStatus.AUTHORIZED.value
    assert len(p_data["quotes"]) >= 2
    assert p_data["recommendation"] is not None
    assert p_data["selected_quote_id"] is not None


@pytest.mark.asyncio
async def test_procurement_requires_approval_and_human_signoff(async_client):
    # 1. Register Admin User
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "finance@enterprise.com",
            "password": "Password123!",
            "full_name": "Finance Director",
            "organization_name": "Enterprise AI",
        },
    )
    admin_token = reg_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Create Agent
    agent_res = await async_client.post(
        "/api/v1/agents",
        headers=admin_headers,
        json={"name": "HeavyComputeAgent"},
    )
    agent_id = agent_res.json()["agent"]["id"]
    raw_key = agent_res.json()["credentials"]["raw_api_key"]
    agent_headers = {"X-Agent-API-Key": raw_key}

    # 3. Create Budget ($10,000)
    await async_client.post(
        "/api/v1/budgets",
        headers=admin_headers,
        json={"name": "Corp Budget", "allocated_amount": "10000.00", "currency": "USD"},
    )

    # 4. Create Policy: Max $1000 per tx, threshold $200
    policy_res = await async_client.post(
        "/api/v1/policies",
        headers=admin_headers,
        json={
            "name": "Standard Spend Policy",
            "max_amount_per_transaction": "1000.00",
            "max_amount_per_day": "5000.00",
            "approval_threshold_amount": "200.00",
            "allowed_suppliers": ["mock_supplier_a", "mock_supplier_b"],
            "allowed_currencies": ["USD"],
        },
    )
    policy_id = policy_res.json()["id"]

    await async_client.post(
        f"/api/v1/policies/assignments/{agent_id}",
        headers=admin_headers,
        json={"policy_id": policy_id},
    )

    # 5. Agent submits purchase for 3 compute nodes ($120 * 3 = $360 > $200 threshold)
    purchase_res = await async_client.post(
        "/api/v1/purchases",
        headers=agent_headers,
        json={
            "item_description": "Cluster worker nodes",
            "category": "compute",
            "max_budget": "500.00",
            "currency": "USD",
            "requirements": {"quantity": 3},
        },
    )
    assert purchase_res.status_code == 201
    p_data = purchase_res.json()
    purchase_id = p_data["id"]
    assert p_data["status"] == PurchaseStatus.REQUIRES_APPROVAL.value

    # 6. Admin checks pending approvals
    approvals_res = await async_client.get("/api/v1/approvals", headers=admin_headers)
    assert approvals_res.status_code == 200
    approvals = approvals_res.json()
    assert len(approvals) == 1
    approval_id = approvals[0]["id"]
    assert approvals[0]["purchase_request_id"] == purchase_id

    # 7. Admin approves the purchase
    decide_res = await async_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=admin_headers,
        json={"decision": "APPROVE", "notes": "Approved for sprint 42 load test"},
    )
    assert decide_res.status_code == 200
    assert decide_res.json()["status"] == ApprovalStatus.APPROVED.value

    # 8. Check purchase status is now AUTHORIZED
    check_pr = await async_client.get(f"/api/v1/purchases/{purchase_id}", headers=admin_headers)
    assert check_pr.status_code == 200
    assert check_pr.json()["status"] == PurchaseStatus.AUTHORIZED.value
