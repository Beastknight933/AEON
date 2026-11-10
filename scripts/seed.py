import asyncio
import sys
import os

# Add root folder to sys.path so app imports work
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from app.core.database import AsyncSessionLocal
from app.core.constants import UserRole
from app.core.security import hash_password, generate_agent_api_key
from app.models.organization import Organization, User, Membership
from app.models.agent import Agent, AgentCredential


async def seed():
    print("Starting AEON database seeding (Milestone 1)...")
    async with AsyncSessionLocal() as session:
        # 1. Check or create Organization
        org_name = "Acme Autonomous Corp"
        org_slug = "acme-autonomous-corp"
        stmt_org = select(Organization).where(Organization.slug == org_slug)
        org = await session.scalar(stmt_org)
        if not org:
            org = Organization(name=org_name, slug=org_slug)
            session.add(org)
            await session.flush()
            print(f"[CREATED] Organization: {org.name} (ID: {org.id})")
        else:
            print(f"[EXISTS] Organization: {org.name} (ID: {org.id})")

        # 2. Check or create Admin User
        admin_email = "admin@aeon.local"
        stmt_user = select(User).where(User.email == admin_email)
        admin = await session.scalar(stmt_user)
        if not admin:
            admin = User(
                email=admin_email,
                full_name="Default Administrator",
                hashed_password=hash_password("AeonAdmin2026!"),
                is_active=True,
            )
            session.add(admin)
            await session.flush()
            print(f"[CREATED] Admin User: {admin.email} (ID: {admin.id})")

            # Create Admin Membership
            membership = Membership(
                user_id=admin.id,
                organization_id=org.id,
                role=UserRole.ADMIN,
            )
            session.add(membership)
            await session.flush()
            print(f"[ASSIGNED] ADMIN role for {admin.email} in {org.name}")
        else:
            print(f"[EXISTS] Admin user: {admin.email} (ID: {admin.id})")

        # 3. Check or create initial Autonomous Agent
        agent_name = "ProcurementBot-Alpha"
        stmt_agent = select(Agent).where(
            Agent.name == agent_name,
            Agent.organization_id == org.id,
        )
        agent = await session.scalar(stmt_agent)
        raw_key = None
        if not agent:
            agent = Agent(
                organization_id=org.id,
                name=agent_name,
                description="Primary autonomous agent for infrastructure purchasing",
                is_active=True,
            )
            session.add(agent)
            await session.flush()

            # Generate individual API credential
            raw_key, prefix, key_hash = generate_agent_api_key()
            cred = AgentCredential(
                agent_id=agent.id,
                organization_id=org.id,
                key_prefix=prefix,
                key_hash=key_hash,
                is_revoked=False,
            )
            session.add(cred)
            await session.flush()
            print(f"[CREATED] Agent: {agent.name} (ID: {agent.id})")
        else:
            print(f"[EXISTS] Agent: {agent.name} (ID: {agent.id})")

        await session.commit()

        print("\n" + "=" * 60)
        print("SEEDING COMPLETED SUCCESSFULLY")
        print("=" * 60)
        print(f"Organization ID : {org.id}")
        print(f"Admin Email     : {admin_email}")
        print(f"Admin Password  : AeonAdmin2026!")
        print(f"Agent ID        : {agent.id}")
        if raw_key:
            print(f"Agent API Key   : {raw_key}")
            print("Notice: Store this API Key securely! It cannot be retrieved again.")
        print("=" * 60 + "\n")


if __name__ == "__main__":
    asyncio.run(seed())
