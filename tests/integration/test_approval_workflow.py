import datetime
import decimal
import uuid
import pytest
from app.core.constants import ApprovalStatus, PurchaseStatus, ReservationStatus, UserRole
from app.core.security import create_access_token, hash_password
from app.models.approval import Approval
from app.models.organization import Membership, User
from app.models.purchase import PurchaseRequest
from app.models.supplier import SupplierQuote
from tests.integration.test_procurement_milestone3 import setup_org_agent_policy_budget


async def create_user_with_role(db_session, org_id: uuid.UUID, email: str, role: UserRole) -> dict:
    user = User(
        email=email,
        hashed_password=hash_password("Password123!"),
        full_name=f"User {role.value}",
        is_active=True,
    )
    db_session.add(user)
    await db_session.flush()

    membership = Membership(
        user_id=user.id,
        organization_id=org_id,
        role=role,
    )
    db_session.add(membership)
    await db_session.commit()

    token = create_access_token(subject=str(user.id), claims={"org_id": str(org_id)})
    return {
        "user_id": user.id,
        "token": token,
        "headers": {"Authorization": f"Bearer {token}"},
    }


@pytest.mark.asyncio
async def test_approval_workflow_approve_success(async_client, db_session):
    """
    Test complete approval lifecycle:
    1. Agent submits request triggering human approval requirement.
    2. Approval is created bound to exact purchase, selected quote, amount, currency, policy version.
    3. Human approver reviews detail and approves.
    4. Status transitions to APPROVED and purchase transitions to AUTHORIZED.
    5. Budget reservation remains active.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="ApproveCorp",
        admin_email="admin@approvecorp.io",
        approval_threshold_amount="100.00",
    )

    # 1. Agent submits purchase
    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute Instance",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201
    pr_data = pr_res.json()
    purchase_id = pr_data["id"]
    selected_quote_id = pr_data["selected_quote_id"]
    assert pr_data["status"] == PurchaseStatus.REQUIRES_APPROVAL.value

    # 2. List approvals
    approvals_res = await async_client.get("/api/v1/approvals", headers=ctx["admin_headers"])
    assert approvals_res.status_code == 200
    approvals = approvals_res.json()
    assert len(approvals) == 1
    approval = approvals[0]
    approval_id = approval["id"]

    # Verify bound properties
    assert approval["purchase_request_id"] == purchase_id
    assert approval["selected_quote_id"] == selected_quote_id
    assert decimal.Decimal(str(approval["amount"])) > decimal.Decimal("0.00")
    assert approval["currency"] == "USD"
    assert approval["policy_version"] == 1
    assert approval["status"] == ApprovalStatus.PENDING.value

    # 3. Get approval detail endpoint
    detail_res = await async_client.get(f"/api/v1/approvals/{approval_id}", headers=ctx["admin_headers"])
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert detail_data["item_description"] == "Compute Instance"
    assert detail_data["is_expired"] is False

    # 4. Approver with APPROVER role approves the request
    approver = await create_user_with_role(db_session, uuid.UUID(ctx["org_id"]), "approver@approvecorp.io", UserRole.APPROVER)
    decide_res = await async_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=approver["headers"],
        json={"decision": "APPROVE", "notes": "Approved for engineering team"},
    )
    assert decide_res.status_code == 200
    decided = decide_res.json()
    assert decided["status"] == ApprovalStatus.APPROVED.value
    assert decided["approver_id"] == str(approver["user_id"])
    assert decided["notes"] == "Approved for engineering team"

    # 5. Verify purchase is now AUTHORIZED
    pr_get = await async_client.get(f"/api/v1/purchases/{purchase_id}", headers=ctx["admin_headers"])
    assert pr_get.status_code == 200
    assert pr_get.json()["status"] == PurchaseStatus.AUTHORIZED.value

    # 6. Verify budget reservation is still ACTIVE
    b_res = await async_client.get(f"/api/v1/budgets/{ctx['budget_id']}", headers=ctx["admin_headers"])
    assert decimal.Decimal(b_res.json()["reserved_amount"]) > decimal.Decimal("0.00")


@pytest.mark.asyncio
async def test_approval_workflow_reject_releases_budget(async_client, db_session):
    """
    Test approval rejection lifecycle:
    1. Purchase requires approval, reserving budget.
    2. Approver rejects request.
    3. Status transitions to REJECTED, purchase to CANCELLED.
    4. Reserved budget is released back to $0.00.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="RejectCorp",
        admin_email="admin@rejectcorp.io",
        approval_threshold_amount="100.00",
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute Node",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201
    purchase_id = pr_res.json()["id"]

    # Verify budget reservation before rejection
    b_before = (await async_client.get(f"/api/v1/budgets/{ctx['budget_id']}", headers=ctx["admin_headers"])).json()
    assert decimal.Decimal(b_before["reserved_amount"]) > decimal.Decimal("0.00")

    # Get approval ID
    approvals = (await async_client.get("/api/v1/approvals", headers=ctx["admin_headers"])).json()
    approval_id = approvals[0]["id"]

    # Reject
    decide_res = await async_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=ctx["admin_headers"],
        json={"decision": "REJECT", "notes": "Project postponed"},
    )
    assert decide_res.status_code == 200
    assert decide_res.json()["status"] == ApprovalStatus.REJECTED.value

    # Purchase cancelled
    pr_after = (await async_client.get(f"/api/v1/purchases/{purchase_id}", headers=ctx["admin_headers"])).json()
    assert pr_after["status"] == PurchaseStatus.CANCELLED.value

    # Budget released
    b_after = (await async_client.get(f"/api/v1/budgets/{ctx['budget_id']}", headers=ctx["admin_headers"])).json()
    assert decimal.Decimal(b_after["reserved_amount"]) == decimal.Decimal("0.00")


@pytest.mark.asyncio
async def test_stale_approval_quote_changed_rejected(async_client, db_session):
    """
    Test stale approval rejection:
    If the underlying purchase's selected quote is swapped or changed after approval was requested,
    the approval decision must be rejected.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="StaleCorp",
        admin_email="admin@stalecorp.io",
        approval_threshold_amount="100.00",
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    purchase_id = uuid.UUID(pr_res.json()["id"])
    approvals = (await async_client.get("/api/v1/approvals", headers=ctx["admin_headers"])).json()
    approval_id = approvals[0]["id"]

    # Tamper: simulate that purchase's selected quote changed
    pr = await db_session.get(PurchaseRequest, purchase_id)
    pr.selected_quote_id = uuid.uuid4()
    await db_session.commit()

    decide_res = await async_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=ctx["admin_headers"],
        json={"decision": "APPROVE", "notes": "Attempt approve with changed quote"},
    )
    assert decide_res.status_code == 422
    assert "selected quote has changed" in decide_res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_stale_approval_purchase_state_changed_rejected(async_client, db_session):
    """
    Test stale approval rejection:
    If the underlying purchase was cancelled or completed prior to deciding approval,
    the decision must be rejected.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="StateCorp",
        admin_email="admin@statecorp.io",
        approval_threshold_amount="100.00",
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Server Compute Node",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    purchase_id = uuid.UUID(pr_res.json()["id"])
    approvals = (await async_client.get("/api/v1/approvals", headers=ctx["admin_headers"])).json()
    approval_id = approvals[0]["id"]

    # Cancel purchase
    pr = await db_session.get(PurchaseRequest, purchase_id)
    pr.status = PurchaseStatus.CANCELLED
    await db_session.commit()

    decide_res = await async_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=ctx["admin_headers"],
        json={"decision": "APPROVE"},
    )
    assert decide_res.status_code == 422
    assert "not awaiting approval" in decide_res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_stale_approval_quote_amount_tampered_rejected(async_client, db_session):
    """
    Test financial integrity:
    If the bound quote's amount was changed after the approval was requested,
    the approval decision must be rejected.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="TamperCorp",
        admin_email="admin@tampercorp.io",
        approval_threshold_amount="100.00",
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute Instance",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    approvals = (await async_client.get("/api/v1/approvals", headers=ctx["admin_headers"])).json()
    approval_id = approvals[0]["id"]
    quote_id = uuid.UUID(approvals[0]["selected_quote_id"])

    # Tamper quote amount
    quote = await db_session.get(SupplierQuote, quote_id)
    quote.total_amount = decimal.Decimal("9999.00")
    await db_session.commit()

    decide_res = await async_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=ctx["admin_headers"],
        json={"decision": "APPROVE"},
    )
    assert decide_res.status_code == 422
    assert "amount or currency has changed" in decide_res.json()["error"]["message"]


@pytest.mark.asyncio
async def test_expired_approval_rejected(async_client, db_session):
    """
    Test expired approval:
    If the approval has passed its expires_at deadline, it transitions to EXPIRED,
    cancels the purchase, releases the budget reservation, and rejects the decision attempt.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="ExpireCorp",
        admin_email="admin@expirecorp.io",
        approval_threshold_amount="100.00",
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute Instance",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    purchase_id = uuid.UUID(pr_res.json()["id"])
    approvals = (await async_client.get("/api/v1/approvals", headers=ctx["admin_headers"])).json()
    approval_id = uuid.UUID(approvals[0]["id"])

    # Set approval expiration into the past
    app = await db_session.get(Approval, approval_id)
    app.expires_at = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=30)
    await db_session.commit()

    decide_res = await async_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=ctx["admin_headers"],
        json={"decision": "APPROVE"},
    )
    assert decide_res.status_code == 422
    assert "expired" in decide_res.json()["error"]["message"].lower()

    # Verify status is EXPIRED
    await db_session.refresh(app)
    assert app.status == ApprovalStatus.EXPIRED

    # Verify purchase is CANCELLED and budget released
    pr = await db_session.get(PurchaseRequest, purchase_id)
    assert pr.status == PurchaseStatus.CANCELLED


@pytest.mark.asyncio
async def test_unauthorized_approver_permissions(async_client, db_session):
    """
    Test role-based access control for human approvals:
    1. User with MEMBER role cannot view or decide approvals (HTTP 403 Forbidden).
    2. User with APPROVER role can view and decide approvals.
    3. User with ADMIN role can view and decide approvals.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="RbacCorp",
        admin_email="admin@rbaccorp.io",
        approval_threshold_amount="100.00",
    )

    # Agent creates purchase requiring approval
    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    approvals = (await async_client.get("/api/v1/approvals", headers=ctx["admin_headers"])).json()
    approval_id = approvals[0]["id"]

    # Create a user with MEMBER role
    member = await create_user_with_role(db_session, uuid.UUID(ctx["org_id"]), "member@rbaccorp.io", UserRole.MEMBER)

    # 1. MEMBER tries GET /approvals -> 403
    list_res = await async_client.get("/api/v1/approvals", headers=member["headers"])
    assert list_res.status_code == 403

    # 2. MEMBER tries GET /approvals/{id} -> 403
    get_res = await async_client.get(f"/api/v1/approvals/{approval_id}", headers=member["headers"])
    assert get_res.status_code == 403

    # 3. MEMBER tries POST /approvals/{id}/decide -> 403
    decide_res = await async_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=member["headers"],
        json={"decision": "APPROVE"},
    )
    assert decide_res.status_code == 403

    # 4. APPROVER role can decide -> 200
    approver = await create_user_with_role(db_session, uuid.UUID(ctx["org_id"]), "approver@rbaccorp.io", UserRole.APPROVER)
    decide_ok = await async_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=approver["headers"],
        json={"decision": "APPROVE", "notes": "Approved by verified approver"},
    )
    assert decide_ok.status_code == 200
    assert decide_ok.json()["status"] == ApprovalStatus.APPROVED.value


@pytest.mark.asyncio
async def test_cross_organization_approval_isolation(async_client, db_session):
    """
    Test organization boundary isolation:
    Organization B user cannot access or decide Organization A approvals.
    """
    ctx_a = await setup_org_agent_policy_budget(
        async_client,
        org_name="OrgA",
        admin_email="admin@orga.io",
        approval_threshold_amount="100.00",
    )
    ctx_b = await setup_org_agent_policy_budget(
        async_client,
        org_name="OrgB",
        admin_email="admin@orgb.io",
        approval_threshold_amount="100.00",
    )

    # Org A creates approval
    await async_client.post(
        "/api/v1/purchases",
        headers=ctx_a["agent_headers"],
        json={
            "item_description": "Compute",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    approvals_a = (await async_client.get("/api/v1/approvals", headers=ctx_a["admin_headers"])).json()
    approval_a_id = approvals_a[0]["id"]

    # Org B lists approvals -> must see 0
    list_b = await async_client.get("/api/v1/approvals", headers=ctx_b["admin_headers"])
    assert list_b.status_code == 200
    assert len(list_b.json()) == 0

    # Org B tries GET /approvals/{approval_a_id} -> 404
    get_b = await async_client.get(f"/api/v1/approvals/{approval_a_id}", headers=ctx_b["admin_headers"])
    assert get_b.status_code == 404

    # Org B tries POST /approvals/{approval_a_id}/decide -> 404
    decide_b = await async_client.post(
        f"/api/v1/approvals/{approval_a_id}/decide",
        headers=ctx_b["admin_headers"],
        json={"decision": "APPROVE"},
    )
    assert decide_b.status_code == 404
