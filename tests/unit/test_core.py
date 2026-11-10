import pytest
from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
    generate_agent_api_key,
    verify_agent_key,
)
from app.core.constants import PurchaseStatus, PaymentStatus, UserRole


@pytest.mark.asyncio
async def test_health_endpoint(async_client):
    response = await async_client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


@pytest.mark.asyncio
async def test_ready_endpoint(async_client):
    response = await async_client.get("/ready")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ready"
    assert data["database"] == "connected"


def test_password_hashing():
    pw = "SuperSecurePassword123!"
    hashed = hash_password(pw)
    assert hashed != pw
    assert verify_password(pw, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_jwt_access_token():
    subject = "user-uuid-12345"
    claims = {"role": UserRole.ADMIN.value, "org_id": "org-uuid-67890"}
    token = create_access_token(subject=subject, claims=claims)
    decoded = decode_access_token(token)
    assert decoded["sub"] == subject
    assert decoded["role"] == UserRole.ADMIN.value
    assert decoded["org_id"] == "org-uuid-67890"


def test_agent_api_key_generation_and_verification():
    raw_key, prefix, key_hash = generate_agent_api_key()
    assert raw_key.startswith("aeon_live_")
    assert prefix == raw_key[:16]
    assert len(key_hash) == 64  # SHA-256 hexdigest
    assert verify_agent_key(raw_key, key_hash) is True
    assert verify_agent_key("aeon_live_invalidkeyhere", key_hash) is False
