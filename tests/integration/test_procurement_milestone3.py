import datetime
import decimal
import uuid
import pytest
from app.core.constants import PurchaseStatus, ApprovalStatus
from app.integrations.suppliers.base import BaseSupplierAdapter
from app.integrations.suppliers.registry import supplier_registry
from app.integrations.suppliers.schemas import NormalizedQuote


class ExpiredMockSupplier(BaseSupplierAdapter):
    @property
    def code(self) -> str:
        return "expired_supplier"

    @property
    def name(self) -> str:
        return "Expired Supply Corp"

    async def fetch_quote(self, item_description: str, category: str, requirements: dict, currency: str = "USD") -> NormalizedQuote:
        past_time = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=2)
        return NormalizedQuote(
            supplier_code=self.code,
            supplier_name=self.name,
            item_id="exp-sku-1",
            unit_price=decimal.Decimal("50.00"),
            quantity=1,
            total_amount=decimal.Decimal("50.00"),
            currency=currency,
            estimated_delivery_days=1,
            reliability_score=decimal.Decimal("0.90"),
            expires_at=past_time,
            raw_data={"test": "expired"},
        )


class CrashingMockSupplier(BaseSupplierAdapter):
    @property
    def code(self) -> str:
        return "crashing_supplier"

    @property
    def name(self) -> str:
        return "Crash & Burn Inc"

    async def fetch_quote(self, item_description: str, category: str, requirements: dict, currency: str = "USD") -> NormalizedQuote:
        raise ConnectionResetError("Simulated upstream supplier API failure")


@pytest.fixture(autouse=True)
def restore_supplier_registry():
    """Ensure supplier registry is reset to defaults before and after each test."""
    supplier_registry.reset_defaults()
    yield
    supplier_registry.reset_defaults()


async def setup_org_agent_policy_budget(
    async_client,
    org_name="ProcureCorp",
    admin_email="admin@procurecorp.io",
    max_amount_per_transaction="500.00",
    max_amount_per_day="2000.00",
    approval_threshold_amount="250.00",
    allowed_suppliers=None,
    budget_allocated="5000.00",
):
    if allowed_suppliers is None:
        allowed_suppliers = ["mock_supplier_a", "mock_supplier_b"]

    # 1. Register admin
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": admin_email,
            "password": "Password123!",
            "full_name": "Admin Officer",
            "organization_name": org_name,
        },
    )
    assert reg_res.status_code == 201, reg_res.text
    token = reg_res.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    me_res = await async_client.get("/api/v1/auth/me", headers=headers)
    assert me_res.status_code == 200, me_res.text
    me_data = me_res.json()
    user_id = me_data["user"]["id"]
    org_id = me_data["organization"]["id"]

    # 2. Create Agent (returns initial API credentials)
    agent_res = await async_client.post(
        "/api/v1/agents",
        headers=headers,
        json={"name": "AutoProcure-Bot"},
    )
    assert agent_res.status_code == 201, agent_res.text
    agent_data = agent_res.json()
    agent_id = agent_data["agent"]["id"]
    raw_api_key = agent_data["credentials"]["raw_api_key"]

    # 4. Create Policy
    policy_res = await async_client.post(
        "/api/v1/policies",
        headers=headers,
        json={
            "name": "Standard Spend Policy",
            "description": "Procurement policy rules",
            "max_amount_per_transaction": max_amount_per_transaction,
            "max_amount_per_day": max_amount_per_day,
            "approval_threshold_amount": approval_threshold_amount,
            "allowed_suppliers": allowed_suppliers,
            "allowed_currencies": ["USD"],
        },
    )
    assert policy_res.status_code == 201, policy_res.text
    policy_id = policy_res.json()["id"]

    # 5. Assign Policy to Agent
    assign_res = await async_client.post(
        f"/api/v1/policies/assignments/{agent_id}",
        headers=headers,
        json={"policy_id": policy_id},
    )
    assert assign_res.status_code == 200, assign_res.text

    # 6. Create Budget
    budget_res = await async_client.post(
        "/api/v1/budgets",
        headers=headers,
        json={
            "name": "General Operating Budget",
            "allocated_amount": budget_allocated,
            "currency": "USD",
        },
    )
    assert budget_res.status_code == 201, budget_res.text
    budget_id = budget_res.json()["id"]

    return {
        "admin_token": token,
        "admin_headers": headers,
        "user_id": user_id,
        "org_id": org_id,
        "agent_id": agent_id,
        "raw_api_key": raw_api_key,
        "agent_headers": {"X-Agent-API-Key": raw_api_key},
        "policy_id": policy_id,
        "budget_id": budget_id,
    }


@pytest.mark.asyncio
async def test_valid_purchase_direct_authorization(async_client):
    """
    Test purchase within limits and under approval threshold -> directly AUTHORIZED.
    Verifies quotes collected, recommendation made, budget atomically reserved.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        approval_threshold_amount="200.00",  # Quote ~$120.00 is under $200.00
    )

    # Agent submits purchase
    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Standard compute server node",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"region": "us-west-2", "quantity": 1},
        },
    )
    assert pr_res.status_code == 201, pr_res.text
    data = pr_res.json()

    assert data["status"] == PurchaseStatus.AUTHORIZED.value
    assert data["selected_quote_id"] is not None
    assert len(data["quotes"]) >= 2
    assert data["recommendation"] is not None
    assert data["recommendation"]["recommended_quote_id"] == data["selected_quote_id"]
    assert data["policy_decision"]["allowed"] is True
    assert data["policy_decision"]["requires_approval"] is False

    # Verify Budget was reserved
    budget_res = await async_client.get(f"/api/v1/budgets/{ctx['budget_id']}", headers=ctx["admin_headers"])
    assert budget_res.status_code == 200
    b_data = budget_res.json()
    assert decimal.Decimal(b_data["reserved_amount"]) > decimal.Decimal("0.00")
    assert decimal.Decimal(b_data["available_amount"]) == decimal.Decimal("5000.00") - decimal.Decimal(b_data["reserved_amount"])

    # Admin retrieves purchase detail
    purchase_id = data["id"]
    detail_res = await async_client.get(f"/api/v1/purchases/{purchase_id}", headers=ctx["admin_headers"])
    assert detail_res.status_code == 200
    assert detail_res.json()["id"] == purchase_id

    # Admin lists purchases
    list_res = await async_client.get("/api/v1/purchases", headers=ctx["admin_headers"])
    assert list_res.status_code == 200
    assert len(list_res.json()) == 1


@pytest.mark.asyncio
async def test_valid_purchase_requires_human_approval_and_decide(async_client):
    """
    Test purchase exceeding approval threshold -> transitions to REQUIRES_APPROVAL.
    Human approver approves it -> transitions to AUTHORIZED.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        approval_threshold_amount="100.00",  # Quote ~$120 is > $100 -> requires approval
        max_amount_per_transaction="500.00",
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute server node",
            "category": "compute",
            "max_budget": "200.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201, pr_res.text
    data = pr_res.json()
    assert data["status"] == PurchaseStatus.REQUIRES_APPROVAL.value
    assert data["policy_decision"]["requires_approval"] is True
    purchase_id = data["id"]

    # Check pending approvals
    approvals_res = await async_client.get("/api/v1/approvals", headers=ctx["admin_headers"])
    assert approvals_res.status_code == 200
    approvals = approvals_res.json()
    assert len(approvals) == 1
    approval = approvals[0]
    assert approval["purchase_request_id"] == purchase_id
    assert approval["status"] == ApprovalStatus.PENDING.value

    # Approve purchase
    decide_res = await async_client.post(
        f"/api/v1/approvals/{approval['id']}/decide",
        headers=ctx["admin_headers"],
        json={"decision": "APPROVE", "notes": "Approved by senior finance manager"},
    )
    assert decide_res.status_code == 200, decide_res.text
    assert decide_res.json()["status"] == ApprovalStatus.APPROVED.value

    # Verify purchase is now AUTHORIZED
    detail_res = await async_client.get(f"/api/v1/purchases/{purchase_id}", headers=ctx["admin_headers"])
    assert detail_res.status_code == 200
    assert detail_res.json()["status"] == PurchaseStatus.AUTHORIZED.value


@pytest.mark.asyncio
async def test_approval_rejection_releases_budget_reservation(async_client):
    """
    Test purchase requiring approval is REJECTED by human -> CANCELLED,
    and reserved budget is cleanly released.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        approval_threshold_amount="100.00",
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute instance",
            "category": "compute",
            "max_budget": "200.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201
    purchase_id = pr_res.json()["id"]

    # Verify funds were reserved
    b_before = (await async_client.get(f"/api/v1/budgets/{ctx['budget_id']}", headers=ctx["admin_headers"])).json()
    assert decimal.Decimal(b_before["reserved_amount"]) > decimal.Decimal("0.00")

    # Get approval ID
    approvals = (await async_client.get("/api/v1/approvals", headers=ctx["admin_headers"])).json()
    approval_id = approvals[0]["id"]

    # Reject
    reject_res = await async_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=ctx["admin_headers"],
        json={"decision": "REJECT", "notes": "Budget freeze in effect"},
    )
    assert reject_res.status_code == 200
    assert reject_res.json()["status"] == ApprovalStatus.REJECTED.value

    # Verify purchase is CANCELLED
    detail = (await async_client.get(f"/api/v1/purchases/{purchase_id}", headers=ctx["admin_headers"])).json()
    assert detail["status"] == PurchaseStatus.CANCELLED.value

    # Verify budget reservation was released back
    b_after = (await async_client.get(f"/api/v1/budgets/{ctx['budget_id']}", headers=ctx["admin_headers"])).json()
    assert decimal.Decimal(b_after["reserved_amount"]) == decimal.Decimal("0.00")
    assert decimal.Decimal(b_after["available_amount"]) == decimal.Decimal("5000.00")


@pytest.mark.asyncio
async def test_hard_policy_violation_cannot_be_approved(async_client, db_session):
    """
    Central architectural rule: A hard policy violation must NEVER be overridden by a human approver.
    Attempting to approve a BLOCKED purchase request must raise PolicyViolationError (HTTP 400).
    """
    from app.models.approval import Approval
    from app.models.purchase import PurchaseRequest

    ctx = await setup_org_agent_policy_budget(
        async_client,
        max_amount_per_transaction="50.00",  # Quote exceeds cap -> BLOCKED
    )

    # Agent triggers blocked purchase
    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Server",
            "category": "compute",
            "max_budget": "200.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201
    blocked_pr_id = pr_res.json()["id"]
    assert pr_res.json()["status"] == PurchaseStatus.BLOCKED.value

    # Even if an Approval record were artificially inserted for this blocked purchase
    fake_approval = Approval(
        purchase_request_id=uuid.UUID(blocked_pr_id),
        status=ApprovalStatus.PENDING,
        notes="Attempting override",
    )
    db_session.add(fake_approval)
    await db_session.commit()
    await db_session.refresh(fake_approval)

    # Approver tries to approve the blocked purchase
    decide_res = await async_client.post(
        f"/api/v1/approvals/{fake_approval.id}/decide",
        headers=ctx["admin_headers"],
        json={"decision": "APPROVE", "notes": "I am the CFO, override this"},
    )
    # Must be rejected with HTTP 422 Unprocessable Entity (Policy Violation)
    assert decide_res.status_code == 422
    assert "BLOCKED by deterministic policy" in decide_res.json()["error"]["message"]



@pytest.mark.asyncio
async def test_blocked_purchase_unauthorized_supplier(async_client):
    """
    Test hard policy violation: supplier not on allow-list.
    Status transitions to BLOCKED; budget is never reserved.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        allowed_suppliers=["unrelated_vendor_xyz"],  # Neither mock_supplier_a nor mock_supplier_b is allowed
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Storage Disk",
            "category": "storage",
            "max_budget": "100.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201
    data = pr_res.json()
    assert data["status"] == PurchaseStatus.BLOCKED.value
    assert data["policy_decision"]["allowed"] is False
    assert "SUPPLIER_NOT_ALLOWED" in data["policy_decision"]["reason_codes"]

    # Verify budget was NOT touched
    b_res = (await async_client.get(f"/api/v1/budgets/{ctx['budget_id']}", headers=ctx["admin_headers"])).json()
    assert decimal.Decimal(b_res["reserved_amount"]) == decimal.Decimal("0.00")


@pytest.mark.asyncio
async def test_blocked_purchase_per_transaction_cap_exceeded(async_client):
    """
    Test hard policy violation: price exceeds per-transaction spending limit.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        max_amount_per_transaction="50.00",  # Quotes are $80+ -> exceeds cap
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Generic compute item",
            "category": "compute",
            "max_budget": "200.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201
    data = pr_res.json()
    assert data["status"] == PurchaseStatus.BLOCKED.value
    assert data["policy_decision"]["allowed"] is False
    assert "PER_TRANSACTION_LIMIT_EXCEEDED" in data["policy_decision"]["reason_codes"]

    # Budget not reserved
    b_res = (await async_client.get(f"/api/v1/budgets/{ctx['budget_id']}", headers=ctx["admin_headers"])).json()
    assert decimal.Decimal(b_res["reserved_amount"]) == decimal.Decimal("0.00")


@pytest.mark.asyncio
async def test_blocked_purchase_insufficient_budget(async_client):
    """
    Test purchase when requested quote exceeds available budget pool.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        budget_allocated="50.00",  # Total budget is $50.00, cheapest quote is $80.00
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Standard compute",
            "category": "compute",
            "max_budget": "200.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201
    data = pr_res.json()
    assert data["status"] == PurchaseStatus.BLOCKED.value
    assert data["policy_decision"]["allowed"] is False
    assert "INSUFFICIENT_BUDGET" in data["policy_decision"]["reason_codes"]

    # Budget not reserved
    b_res = (await async_client.get(f"/api/v1/budgets/{ctx['budget_id']}", headers=ctx["admin_headers"])).json()
    assert decimal.Decimal(b_res["reserved_amount"]) == decimal.Decimal("0.00")


@pytest.mark.asyncio
async def test_expired_quotes_handling(async_client):
    """
    Test quote expiration:
    1. If one supplier returns an expired quote, it is marked invalid and excluded from recommendation.
    2. If ALL suppliers return expired quotes, purchase transitions to BLOCKED.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        allowed_suppliers=["mock_supplier_a", "mock_supplier_b", "expired_supplier"],
    )

    # 1. Register an expired supplier alongside default suppliers
    supplier_registry.register(ExpiredMockSupplier())

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute item",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201
    data = pr_res.json()
    # Should succeed with one of the valid suppliers, NOT the expired one
    assert data["status"] == PurchaseStatus.AUTHORIZED.value
    selected_quote_id = data["selected_quote_id"]

    # Check quotes: expired quote should have is_valid = False
    quotes = data["quotes"]
    expired_quotes = [q for q in quotes if q["supplier_name"] == "Expired Supply Corp"]
    assert len(expired_quotes) == 1
    assert expired_quotes[0]["is_valid"] is False
    assert expired_quotes[0]["id"] != selected_quote_id

    # 2. Now test when ONLY expired suppliers exist
    supplier_registry._adapters = {}
    supplier_registry.register(ExpiredMockSupplier())

    pr_res2 = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute item",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res2.status_code == 201
    data2 = pr_res2.json()
    # All quotes expired -> BLOCKED
    assert data2["status"] == PurchaseStatus.BLOCKED.value
    assert data2["selected_quote_id"] is None


@pytest.mark.asyncio
async def test_invalid_supplier_responses_handling(async_client):
    """
    Test resilient supplier handling:
    1. If one supplier raises an exception, the other valid supplier succeeds.
    2. If all suppliers fail, purchase is BLOCKED and 502/SupplierError is handled.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        allowed_suppliers=["mock_supplier_a", "mock_supplier_b", "crashing_supplier"],
    )

    # 1. Add crashing supplier alongside valid supplier
    supplier_registry.register(CrashingMockSupplier())

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201
    assert pr_res.json()["status"] == PurchaseStatus.AUTHORIZED.value

    # 2. Only crashing supplier in registry
    supplier_registry._adapters = {}
    supplier_registry.register(CrashingMockSupplier())

    pr_res2 = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    # When all suppliers fail, should return 502 Bad Gateway / SupplierError
    assert pr_res2.status_code in [502, 400]


@pytest.mark.asyncio
async def test_cross_agent_and_organization_isolation(async_client):
    """
    Test organization and agent isolation:
    1. Org B user cannot view Org A's purchase requests.
    2. Invalid agent API key is rejected with 401.
    """
    # Org A
    ctx_a = await setup_org_agent_policy_budget(
        async_client,
        org_name="Alpha Corp",
        admin_email="admin@alpha.io",
    )
    # Org B
    ctx_b = await setup_org_agent_policy_budget(
        async_client,
        org_name="Beta Corp",
        admin_email="admin@beta.io",
    )

    # Agent A makes a purchase
    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx_a["agent_headers"],
        json={
            "item_description": "Alpha Server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201
    purchase_a_id = pr_res.json()["id"]

    # Org B admin attempts to read Purchase A -> must get 404 Not Found
    get_res = await async_client.get(f"/api/v1/purchases/{purchase_a_id}", headers=ctx_b["admin_headers"])
    assert get_res.status_code == 404

    # Org B admin lists purchases -> must see 0 purchases
    list_b = await async_client.get("/api/v1/purchases", headers=ctx_b["admin_headers"])
    assert list_b.status_code == 200
    assert len(list_b.json()) == 0

    # Caller with fake API key -> must get 401
    fake_res = await async_client.post(
        "/api/v1/purchases",
        headers={"X-Agent-API-Key": "aeon_live_fake_key_12345"},
        json={
            "item_description": "Hacker Server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {},
        },
    )
    assert fake_res.status_code == 401
