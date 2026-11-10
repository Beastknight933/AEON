import pytest


@pytest.mark.asyncio
async def test_register_and_login_flow(async_client):
    # 1. Register
    reg_payload = {
        "email": "ceo@innovate.ai",
        "password": "StrongPassword123!",
        "full_name": "Chief Executive",
        "organization_name": "Innovate AI Labs",
    }
    reg_res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert "access_token" in reg_data

    token = reg_data["access_token"]

    # 2. Duplicate registration fails
    dup_res = await async_client.post("/api/v1/auth/register", json=reg_payload)
    assert dup_res.status_code == 409
    assert dup_res.json()["error"]["code"] == "RESOURCE_CONFLICT"

    # 3. Check /auth/me
    headers = {"Authorization": f"Bearer {token}"}
    me_res = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["user"]["email"] == "ceo@innovate.ai"
    assert me_data["role"] == "ADMIN"
    assert me_data["organization"]["name"] == "Innovate AI Labs"

    # 4. Login with valid credentials
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "ceo@innovate.ai", "password": "StrongPassword123!"},
    )
    assert login_res.status_code == 200
    assert "access_token" in login_res.json()

    # 5. Login with invalid password
    bad_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "ceo@innovate.ai", "password": "WrongPassword!"},
    )
    assert bad_login.status_code == 401
    assert bad_login.json()["error"]["code"] == "INVALID_CREDENTIALS"
