import pytest
from app.api.deps import get_authenticated_agent
from app.core.errors import AuthenticationError


@pytest.mark.asyncio
async def test_agent_management_and_authentication(async_client, db_session):
    # 1. Register admin user
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "lead@robotics.io",
            "password": "Password123!",
            "full_name": "Tech Lead",
            "organization_name": "Autonomous Systems Org",
        },
    )
    token = reg_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {token}"}

    # 2. Create agent
    agent_res = await async_client.post(
        "/api/v1/agents",
        headers=admin_headers,
        json={
            "name": "AutoCloudProvisioner",
            "description": "Agent handling cloud purchases",
        },
    )
    assert agent_res.status_code == 201
    agent_data = agent_res.json()
    agent_id = agent_data["agent"]["id"]
    raw_key = agent_data["credentials"]["raw_api_key"]
    assert raw_key.startswith("aeon_live_")

    # 3. Test agent authentication using raw key via helper
    agent_record, cred, org = await get_authenticated_agent(
        db=db_session,
        x_agent_api_key=raw_key,
        auth_header=None,
    )
    assert str(agent_record.id) == agent_id
    assert cred.is_revoked is False
    assert org.name == "Autonomous Systems Org"

    # 4. List agents
    list_res = await async_client.get("/api/v1/agents", headers=admin_headers)
    assert list_res.status_code == 200
    agents = list_res.json()
    assert len(agents) == 1
    assert agents[0]["id"] == agent_id

    # 5. Rotate key
    rotate_res = await async_client.post(
        f"/api/v1/agents/{agent_id}/keys/rotate",
        headers=admin_headers,
    )
    assert rotate_res.status_code == 200
    new_raw_key = rotate_res.json()["raw_api_key"]
    assert new_raw_key != raw_key

    # Old key must now fail authentication
    with pytest.raises(AuthenticationError):
        await get_authenticated_agent(db=db_session, x_agent_api_key=raw_key, auth_header=None)

    # New key succeeds
    agent_record2, _, _ = await get_authenticated_agent(
        db=db_session, x_agent_api_key=new_raw_key, auth_header=None
    )
    assert str(agent_record2.id) == agent_id
