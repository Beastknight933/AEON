import uuid
import pytest
from sqlalchemy import select
from app.models import (
    Organization,
    User,
    Membership,
    Agent,
    AgentCredential,
)
from app.core.constants import UserRole


@pytest.mark.asyncio
async def test_create_and_query_identity_entities(db_session):
    # 1. Organization
    org = Organization(name="Acme Autonomous Corp", slug="acme-corp")
    db_session.add(org)
    await db_session.flush()
    assert org.id is not None
    assert org.name == "Acme Autonomous Corp"

    # 2. User & Membership
    user = User(
        email="admin@acme.com",
        hashed_password="hashed_pw_argon2",
        full_name="Alice Admin",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    membership = Membership(
        user_id=user.id,
        organization_id=org.id,
        role=UserRole.ADMIN,
    )
    db_session.add(membership)
    await db_session.flush()

    # 3. Agent & Credential
    agent = Agent(
        organization_id=org.id,
        name="ProcurementBot-9000",
        description="Autonomous cloud resource procurement agent",
        is_active=True,
    )
    db_session.add(agent)
    await db_session.flush()

    cred = AgentCredential(
        agent_id=agent.id,
        organization_id=org.id,
        key_prefix="aeon_live_test12",
        key_hash="a" * 64,
        is_revoked=False,
    )
    db_session.add(cred)
    await db_session.commit()

    # 4. Verify querying relationships
    stmt = select(Agent).where(Agent.id == agent.id)
    queried_agent = await db_session.scalar(stmt)
    assert queried_agent is not None
    assert queried_agent.name == "ProcurementBot-9000"
    assert queried_agent.organization_id == org.id

    stmt_user = select(User).where(User.email == "admin@acme.com")
    queried_user = await db_session.scalar(stmt_user)
    assert queried_user is not None
    assert queried_user.full_name == "Alice Admin"
