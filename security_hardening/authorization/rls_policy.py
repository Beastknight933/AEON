"""PostgreSQL Row-Level Security (RLS) Design, Helpers, and Activation Guide."""

import uuid
from typing import Optional
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class RLSContextManager:
    """Safely injects current organization context into PostgreSQL session for RLS evaluation."""

    @staticmethod
    async def set_tenant_context(session: AsyncSession, organization_id: uuid.UUID) -> None:
        """Set session-level tenant parameter.

        In PostgreSQL, RLS policies evaluate `current_setting('app.current_organization_id', true)::uuid`.
        """
        stmt = text("SET LOCAL app.current_organization_id = :org_id")
        await session.execute(stmt, {"org_id": str(organization_id)})


# Reference DDL SQL for PostgreSQL RLS activation
POSTGRESQL_RLS_MIGRATION_SQL = """
-- ============================================================================
-- AEON PostgreSQL Row-Level Security (RLS) Tenant Isolation Policies
-- Prerequisites: Verify that Supabase session pooler (port 5432) or transaction pooler
-- is configured so that 'SET LOCAL app.current_organization_id' persists across queries.
-- ============================================================================

-- 1. Enable RLS on core multi-tenant tables
ALTER TABLE organizations ENABLE ROW LEVEL SECURITY;
ALTER TABLE agents ENABLE ROW LEVEL SECURITY;
ALTER TABLE agent_credentials ENABLE ROW LEVEL SECURITY;
ALTER TABLE policies ENABLE ROW LEVEL SECURITY;
ALTER TABLE budgets ENABLE ROW LEVEL SECURITY;
ALTER TABLE budget_reservations ENABLE ROW LEVEL SECURITY;
ALTER TABLE purchase_requests ENABLE ROW LEVEL SECURITY;
ALTER TABLE supplier_quotes ENABLE ROW LEVEL SECURITY;
ALTER TABLE approvals ENABLE ROW LEVEL SECURITY;
ALTER TABLE transactions ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY;

-- 2. Define Tenant Isolation Policies for Agents table
CREATE POLICY tenant_isolation_agents ON agents
    FOR ALL
    USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid);

-- 3. Define Tenant Isolation Policies for Purchase Requests table
CREATE POLICY tenant_isolation_purchases ON purchase_requests
    FOR ALL
    USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid);

-- 4. Define Tenant Isolation Policies for Budgets table
CREATE POLICY tenant_isolation_budgets ON budgets
    FOR ALL
    USING (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid)
    WITH CHECK (organization_id = NULLIF(current_setting('app.current_organization_id', true), '')::uuid);

-- 5. Bypass policy for background superuser/migrator roles
-- ALTER TABLE agents FORCE ROW LEVEL SECURITY;
"""

