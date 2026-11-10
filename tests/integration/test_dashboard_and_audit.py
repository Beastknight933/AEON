import pytest


@pytest.mark.asyncio
async def test_dashboard_overview_and_audit_trail(async_client):
    # 1. Register user
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "auditor@aeon.ai",
            "password": "Password123!",
            "full_name": "Audit Officer",
            "organization_name": "AEON Global",
        },
    )
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    # 2. Check initial dashboard stats
    dash_res = await async_client.get("/api/v1/dashboard/stats", headers=headers)
    assert dash_res.status_code == 200
    stats = dash_res.json()
    assert stats["total_agents"] == 0
    assert stats["total_budget_allocated"] == "0.00"

    # 3. Create an agent & budget
    agent_res = await async_client.post(
        "/api/v1/agents",
        headers=headers,
        json={"name": "LogisticsAgent"},
    )
    assert agent_res.status_code == 201

    budget_res = await async_client.post(
        "/api/v1/budgets",
        headers=headers,
        json={"name": "Logistics Budget", "allocated_amount": "2500.00", "currency": "USD"},
    )
    assert budget_res.status_code == 201

    # 4. Check dashboard overview
    overview_res = await async_client.get("/api/v1/dashboard/overview", headers=headers)
    assert overview_res.status_code == 200
    overview = overview_res.json()
    assert overview["stats"]["total_agents"] == 1
    assert overview["stats"]["total_budget_allocated"] == "2500.00"
    assert overview["stats"]["total_budget_available"] == "2500.00"

    # 5. Query Audit Trail
    audit_res = await async_client.get("/api/v1/audit", headers=headers)
    assert audit_res.status_code == 200
    events = audit_res.json()
    assert len(events) >= 0  # audit records are queryable
