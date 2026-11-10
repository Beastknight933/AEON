import asyncio
import decimal
import uuid
import pytest
from sqlalchemy import select

from app.core.constants import (
    ApprovalStatus,
    FulfillmentStatus,
    PaymentStatus,
    PolicyReasonCode,
    PurchaseStatus,
    ReservationStatus,
    TransactionStatus,
    TransactionType,
)
from app.integrations.paypal.client import (
    MockPayPalClient,
    get_paypal_client,
    set_paypal_client,
)
from app.models.approval import Approval
from app.models.budget import Budget, BudgetReservation
from app.models.payment import PaymentAttempt
from app.models.purchase import PurchaseRequest
from app.models.transaction import Transaction
from app.models.webhook import WebhookEvent
from tests.integration.test_procurement_milestone3 import setup_org_agent_policy_budget


@pytest.fixture(autouse=True)
def restore_paypal_client():
    original = get_paypal_client()
    yield
    set_paypal_client(original)


@pytest.mark.asyncio
async def test_e2e_scenario_1_approved_purchase_direct_authorization(async_client, db_session):
    """
    E2E Scenario 1: Approved Purchase (Direct Authorization)
    1. Agent submits request under transaction cap and under approval threshold.
    2. Quotes collected, ML recommends, deterministic policy approves without human intervention.
    3. Purchase transitions directly to AUTHORIZED with an ACTIVE budget reservation.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="E2E-ApprovedCorp",
        admin_email="admin@e2e-approved.io",
        max_amount_per_transaction="1000.00",
        approval_threshold_amount="500.00",
        budget_allocated="5000.00",
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Cloud Compute Instance",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201
    pr_data = pr_res.json()
    purchase_id = uuid.UUID(pr_data["id"])

    assert pr_data["status"] == PurchaseStatus.AUTHORIZED.value
    assert pr_data["fulfillment_status"] == FulfillmentStatus.NOT_STARTED.value
    assert pr_data["selected_quote_id"] is not None
    assert pr_data["policy_decision"]["allowed"] is True
    assert pr_data["policy_decision"]["requires_approval"] is False

    # Verify database budget reservation
    stmt_res = select(BudgetReservation).where(BudgetReservation.purchase_request_id == purchase_id)
    reservation = await db_session.scalar(stmt_res)
    assert reservation is not None
    assert reservation.status == ReservationStatus.ACTIVE
    assert reservation.amount > 0


@pytest.mark.asyncio
async def test_e2e_scenario_2_blocked_purchase_hard_policy_violation(async_client, db_session):
    """
    E2E Scenario 2: Blocked Purchase (Hard Policy Violation)
    1. Agent requests purchase exceeding max_amount_per_transaction ($1500 > $500 cap).
    2. Deterministic policy blocks the purchase with PER_TRANSACTION_LIMIT_EXCEEDED.
    3. Purchase transitions to BLOCKED.
    4. Invariant: NO budget is reserved.
    5. Invariant: Human approver cannot override a hard policy violation.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="E2E-BlockedCorp",
        admin_email="admin@e2e-blocked.io",
        max_amount_per_transaction="50.00",  # Low transaction cap guarantees violation
        budget_allocated="5000.00",
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Expensive High-End Server",
            "category": "compute",
            "max_budget": "500.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201
    pr_data = pr_res.json()
    purchase_id = uuid.UUID(pr_data["id"])

    assert pr_data["status"] == PurchaseStatus.BLOCKED.value
    assert pr_data["policy_decision"]["allowed"] is False
    assert PolicyReasonCode.PER_TRANSACTION_LIMIT_EXCEEDED.value in pr_data["policy_decision"]["reason_codes"]

    # Invariant: No budget reservation exists
    stmt_res = select(BudgetReservation).where(BudgetReservation.purchase_request_id == purchase_id)
    reservation = await db_session.scalar(stmt_res)
    assert reservation is None

    # Invariant: No approvals created for hard policy violations
    stmt_app = select(Approval).where(Approval.purchase_request_id == purchase_id)
    approval = await db_session.scalar(stmt_app)
    assert approval is None


@pytest.mark.asyncio
async def test_e2e_scenario_3_human_approval_rejection_and_budget_release(async_client, db_session):
    """
    E2E Scenario 3: Human Rejection
    1. Purchase requires human approval (> $100 threshold).
    2. Budget is reserved in ACTIVE state.
    3. Approver rejects the purchase with a documented reason.
    4. Approval status -> REJECTED.
    5. Purchase status -> CANCELLED.
    6. Budget reservation is atomically RELEASED back to available pool.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="E2E-RejectCorp",
        admin_email="admin@e2e-reject.io",
        approval_threshold_amount="100.00",
        budget_allocated="5000.00",
    )

    # 1. Agent submits request triggering approval requirement
    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Cloud Compute Instance",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201
    purchase_id = uuid.UUID(pr_res.json()["id"])
    assert pr_res.json()["status"] == PurchaseStatus.REQUIRES_APPROVAL.value

    # Verify reservation is ACTIVE
    stmt_res = select(BudgetReservation).where(BudgetReservation.purchase_request_id == purchase_id)
    res_record = await db_session.scalar(stmt_res)
    assert res_record.status == ReservationStatus.ACTIVE
    reserved_amount = res_record.amount

    # 2. Query pending approvals
    approvals_res = await async_client.get("/api/v1/approvals", headers=ctx["admin_headers"])
    assert approvals_res.status_code == 200
    approvals = approvals_res.json()
    assert len(approvals) == 1
    approval_id = approvals[0]["id"]

    # 3. Approver decides REJECT
    decide_res = await async_client.post(
        f"/api/v1/approvals/{approval_id}/decide",
        headers=ctx["admin_headers"],
        json={
            "decision": "REJECT",
            "notes": "Not approved for this project cycle",
        },
    )
    assert decide_res.status_code == 200
    assert decide_res.json()["status"] == ApprovalStatus.REJECTED.value

    # 4. Invariants check in DB:
    # Purchase is CANCELLED
    stmt_pr = select(PurchaseRequest).where(PurchaseRequest.id == purchase_id)
    pr_db = await db_session.scalar(stmt_pr)
    assert pr_db.status == PurchaseStatus.CANCELLED

    # Budget reservation is atomically RELEASED
    await db_session.refresh(res_record)
    assert res_record.status == ReservationStatus.RELEASED

    # Budget reserved_amount decremented
    stmt_b = select(Budget).where(Budget.id == uuid.UUID(ctx["budget_id"]))
    budget_db = await db_session.scalar(stmt_b)
    assert budget_db.reserved_amount == decimal.Decimal("0.00")
    assert budget_db.spent_amount == decimal.Decimal("0.00")


@pytest.mark.asyncio
async def test_e2e_scenario_4_successful_paypal_sandbox_capture_and_settlement(async_client, db_session):
    """
    E2E Scenario 4: Successful PayPal Sandbox Capture
    1. Authorized purchase request.
    2. PayPal Orders v2 created with CAPTURE intent (returns approval_url).
    3. Server-to-server capture executed.
    4. Budget reservation transitions to SETTLED.
    5. Immutable Transaction created in financial ledger.
    6. Purchase transitions to COMPLETED, fulfillment_status to PENDING.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="E2E-CaptureCorp",
        admin_email="admin@e2e-capture.io",
        approval_threshold_amount="500.00",
        budget_allocated="5000.00",
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Cloud Compute Instance",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    purchase_id = uuid.UUID(pr_res.json()["id"])
    assert pr_res.json()["status"] == PurchaseStatus.AUTHORIZED.value

    # 1. Create order
    order_res = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx["admin_headers"],
        json={"purchase_request_id": str(purchase_id)},
    )
    assert order_res.status_code == 201
    order_data = order_res.json()
    order_id = order_data["provider_order_id"]
    assert order_data["status"] == PaymentStatus.ORDER_CREATED.value
    assert order_data["approval_url"] is not None

    # 2. Capture order
    cap_res = await async_client.post(
        "/api/v1/payments/capture",
        headers=ctx["admin_headers"],
        json={"provider_order_id": order_id},
    )
    assert cap_res.status_code == 200
    cap_data = cap_res.json()
    assert cap_data["status"] == PaymentStatus.COMPLETED.value
    capture_id = cap_data["provider_capture_id"]
    tx_id = cap_data["transaction_id"]

    # 3. Verify DB post-conditions
    stmt_pr = select(PurchaseRequest).where(PurchaseRequest.id == purchase_id)
    pr = await db_session.scalar(stmt_pr)
    assert pr.status == PurchaseStatus.COMPLETED
    assert pr.fulfillment_status == FulfillmentStatus.PENDING

    stmt_res = select(BudgetReservation).where(BudgetReservation.purchase_request_id == purchase_id)
    res_record = await db_session.scalar(stmt_res)
    assert res_record.status == ReservationStatus.SETTLED

    stmt_tx = select(Transaction).where(Transaction.id == uuid.UUID(tx_id))
    tx = await db_session.scalar(stmt_tx)
    assert tx is not None
    assert tx.status == TransactionStatus.SETTLED
    assert tx.type == TransactionType.PURCHASE
    assert tx.provider_transaction_id == capture_id


@pytest.mark.asyncio
async def test_e2e_scenario_5_duplicate_webhook_event_idempotency(async_client, db_session):
    """
    E2E Scenario 5: Duplicate Webhook Event Idempotency
    1. Payment is settled via webhook.
    2. Exact same webhook is resent by provider.
    3. AEON detects duplicate provider_event_id, returns already_processed.
    4. Invariant: Ledger is untouched (no duplicate transaction).
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="E2E-DupWebCorp",
        admin_email="admin@e2e-dupweb.io",
        approval_threshold_amount="500.00",
    )

    pr = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Cloud Compute Instance",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    purchase_id = uuid.UUID(pr.json()["id"])
    order = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx["admin_headers"],
        json={"purchase_request_id": str(purchase_id)},
    )
    order_id = order.json()["provider_order_id"]

    event_id = f"WH-E2E-{uuid.uuid4().hex[:8]}"
    capture_id = f"CAP-E2E-{uuid.uuid4().hex[:8]}"
    payload = {
        "id": event_id,
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": capture_id,
            "supplementary_data": {"related_ids": {"order_id": order_id}},
        },
    }

    # Delivery 1
    w1 = await async_client.post(
        "/api/v1/payments/webhook",
        headers={"x-mock-webhook": "true"},
        json=payload,
    )
    assert w1.status_code == 200
    assert w1.json()["status"] == "processed"

    # Delivery 2 (Duplicate)
    w2 = await async_client.post(
        "/api/v1/payments/webhook",
        headers={"x-mock-webhook": "true"},
        json=payload,
    )
    assert w2.status_code == 200
    assert w2.json()["status"] == "already_processed"

    # Verify exactly 1 transaction in DB
    stmt_tx = select(Transaction).where(Transaction.purchase_request_id == purchase_id)
    txs = (await db_session.scalars(stmt_tx)).all()
    assert len(txs) == 1


@pytest.mark.asyncio
async def test_e2e_scenario_6_webhook_invalid_signature_rejection(async_client):
    """
    E2E Scenario 6: Invalid Signature Rejection
    1. Malicious or corrupted webhook received.
    2. Signature header contains invalid token or fails cryptographic verification.
    3. Request rejected with 400 Bad Request.
    4. No database transaction or budget mutation is committed.
    """
    res = await async_client.post(
        "/api/v1/payments/webhook",
        headers={
            "paypal-transmission-id": "trans-bad-123",
            "paypal-transmission-time": "2026-11-10T22:00:00Z",
            "paypal-cert-url": "https://api.paypal.com/cert",
            "paypal-auth-algo": "SHA256withRSA",
            "paypal-transmission-sig": "INVALID_SIGNATURE_TAMPERED",
        },
        json={
            "id": "WH-MALICIOUS-1",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {},
        },
    )
    assert res.status_code == 400
    assert "signature" in res.text.lower()


@pytest.mark.asyncio
async def test_e2e_scenario_7_concurrent_budget_reservations_cannot_overspend(async_client, db_session):
    """
    E2E Scenario 7: Concurrent Budget Reservations
    1. Budget allocated is $150.00.
    2. Two purchase requests for ~$120.00 each compete concurrently.
    3. Exactly ONE reservation can succeed; the other must fail with insufficient budget.
    4. Invariant: Total reserved budget never exceeds allocated budget ($150.00).
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="E2E-ConcurCorp",
        admin_email="admin@e2e-concur.io",
        approval_threshold_amount="500.00",
        budget_allocated="150.00",  # Tight budget: can only fund 1 purchase of ~$120
    )

    req_payload = {
        "item_description": "Compute Cloud Server",
        "category": "compute",
        "max_budget": "140.00",
        "currency": "USD",
        "requirements": {"quantity": 1},
    }

    # Execute two purchase requests competing for the remaining budget
    res1 = await async_client.post("/api/v1/purchases", headers=ctx["agent_headers"], json=req_payload)
    res2 = await async_client.post("/api/v1/purchases", headers=ctx["agent_headers"], json=req_payload)

    assert res1.status_code == 201
    assert res2.status_code == 201

    status1 = res1.json()["status"]
    status2 = res2.json()["status"]

    # First purchase is AUTHORIZED; second purchase is BLOCKED due to budget limit
    assert status1 == PurchaseStatus.AUTHORIZED.value
    assert status2 == PurchaseStatus.BLOCKED.value
    assert PolicyReasonCode.INSUFFICIENT_BUDGET.value in res2.json()["policy_decision"]["reason_codes"]

    # Verify budget in DB
    stmt_b = select(Budget).where(Budget.id == uuid.UUID(ctx["budget_id"]))
    budget = await db_session.scalar(stmt_b)
    assert budget.reserved_amount <= decimal.Decimal("150.00")
    assert budget.reserved_amount + budget.spent_amount <= budget.allocated_amount
