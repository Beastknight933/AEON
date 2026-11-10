import decimal
import uuid
import pytest
from sqlalchemy import select

from app.core.constants import (
    PaymentStatus,
    PurchaseStatus,
    ReservationStatus,
    TransactionStatus,
    TransactionType,
)
from app.integrations.paypal.client import (
    MockPayPalClient,
    PayPalClient,
    get_paypal_client,
    set_paypal_client,
)
from app.models.budget import Budget, BudgetReservation
from app.models.payment import PaymentAttempt
from app.models.purchase import PurchaseRequest
from app.models.transaction import Transaction
from tests.integration.test_procurement_milestone3 import setup_org_agent_policy_budget


@pytest.fixture(autouse=True)
def restore_paypal_client():
    """Ensure paypal client is restored to default after each test."""
    original = get_paypal_client()
    yield
    set_paypal_client(original)


@pytest.mark.asyncio
async def test_payment_order_create_and_capture_happy_path(async_client, db_session):
    """
    Test end-to-end payment workflow:
    1. Authorized purchase request with active budget reservation.
    2. PayPal order created with CAPTURE intent (returns approval_url).
    3. PayPal capture succeeds -> settles budget, creates Transaction, completes purchase.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="PayCorp",
        admin_email="admin@paycorp.io",
        approval_threshold_amount="500.00",
        budget_allocated="2000.00",
    )

    # 1. Agent submits purchase request (compute is ~$120 <= $500 threshold, so directly AUTHORIZED)
    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute Cloud Server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201, pr_res.text
    pr_data = pr_res.json()
    purchase_id = uuid.UUID(pr_data["id"])
    assert pr_data["status"] == PurchaseStatus.AUTHORIZED.value

    # Verify reservation is ACTIVE
    stmt_res = select(BudgetReservation).where(BudgetReservation.purchase_request_id == purchase_id)
    res_record = await db_session.scalar(stmt_res)
    assert res_record is not None
    assert res_record.status == ReservationStatus.ACTIVE
    authorized_amount = res_record.amount

    # 2. Create PayPal payment order
    order_res = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx["admin_headers"],
        json={"purchase_request_id": str(purchase_id)},
    )
    assert order_res.status_code == 201, order_res.text
    order_data = order_res.json()
    provider_order_id = order_data["provider_order_id"]
    assert provider_order_id.startswith("ORDER-MOCK-")
    assert order_data["status"] == PaymentStatus.ORDER_CREATED.value
    assert order_data["approval_url"] is not None
    assert "token=" in order_data["approval_url"]
    assert decimal.Decimal(str(order_data["amount"])) == authorized_amount

    # Check PaymentAttempt in DB
    stmt_att = select(PaymentAttempt).where(PaymentAttempt.provider_order_id == provider_order_id)
    attempt = await db_session.scalar(stmt_att)
    assert attempt is not None
    assert attempt.status == PaymentStatus.ORDER_CREATED

    # 3. Capture PayPal payment
    cap_res = await async_client.post(
        "/api/v1/payments/capture",
        headers=ctx["admin_headers"],
        json={"provider_order_id": provider_order_id},
    )
    assert cap_res.status_code == 200, cap_res.text
    cap_data = cap_res.json()
    assert cap_data["status"] == PaymentStatus.COMPLETED.value
    assert cap_data["provider_capture_id"].startswith("CAPTURE-MOCK-")
    assert cap_data["transaction_id"] is not None

    # 4. Verify post-conditions in DB
    await db_session.refresh(attempt)
    assert attempt.status == PaymentStatus.COMPLETED
    assert attempt.provider_capture_id == cap_data["provider_capture_id"]

    stmt_pr = select(PurchaseRequest).where(PurchaseRequest.id == purchase_id)
    pr_db = await db_session.scalar(stmt_pr)
    assert pr_db.status == PurchaseStatus.COMPLETED

    await db_session.refresh(res_record)
    assert res_record.status == ReservationStatus.SETTLED

    stmt_b = select(Budget).where(Budget.id == uuid.UUID(ctx["budget_id"]))
    budget_db = await db_session.scalar(stmt_b)
    assert budget_db.spent_amount == authorized_amount
    assert budget_db.reserved_amount == decimal.Decimal("0.00")

    stmt_tx = select(Transaction).where(Transaction.purchase_request_id == purchase_id)
    tx = await db_session.scalar(stmt_tx)
    assert tx is not None
    assert tx.status == TransactionStatus.SETTLED
    assert tx.type == TransactionType.PURCHASE
    assert tx.amount == authorized_amount


@pytest.mark.asyncio
async def test_payment_capture_and_create_idempotency(async_client, db_session):
    """
    Test idempotency:
    1. Replaying capture returns existing completed response without duplicate transactions.
    2. Calling create-order again returns existing attempt without duplicate records.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="IdemCorp",
        admin_email="admin@idemcorp.io",
        approval_threshold_amount="500.00",
        budget_allocated="2000.00",
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute Cloud Server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    purchase_id = uuid.UUID(pr_res.json()["id"])

    # First create-order
    o1 = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx["admin_headers"],
        json={"purchase_request_id": str(purchase_id)},
    )
    assert o1.status_code == 201
    order_id = o1.json()["provider_order_id"]

    # Replay create-order (should return existing attempt)
    o2 = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx["admin_headers"],
        json={"purchase_request_id": str(purchase_id)},
    )
    assert o2.status_code == 201
    assert o2.json()["provider_order_id"] == order_id
    assert o2.json()["payment_attempt_id"] == o1.json()["payment_attempt_id"]

    # First capture
    c1 = await async_client.post(
        "/api/v1/payments/capture",
        headers=ctx["admin_headers"],
        json={"provider_order_id": order_id},
    )
    assert c1.status_code == 200
    tx_id_1 = c1.json()["transaction_id"]

    # Replay capture (should return same transaction without double spending)
    c2 = await async_client.post(
        "/api/v1/payments/capture",
        headers=ctx["admin_headers"],
        json={"provider_order_id": order_id},
    )
    assert c2.status_code == 200
    assert c2.json()["transaction_id"] == tx_id_1
    assert c2.json()["status"] == PaymentStatus.COMPLETED.value

    # Verify only 1 transaction exists
    stmt_txs = select(Transaction).where(Transaction.purchase_request_id == purchase_id)
    txs = (await db_session.scalars(stmt_txs)).all()
    assert len(txs) == 1


@pytest.mark.asyncio
async def test_payment_create_order_rejected_for_unauthorized_purchase(async_client, db_session):
    """
    Enforce precondition: Purchases that are not AUTHORIZED (e.g. REQUIRES_APPROVAL)
    must NOT be allowed to create payment orders.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="PrecondCorp",
        admin_email="admin@precondcorp.io",
        approval_threshold_amount="50.00",  # Low threshold -> forces REQUIRES_APPROVAL
        budget_allocated="2000.00",
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute Cloud Server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert pr_res.status_code == 201
    assert pr_res.json()["status"] == PurchaseStatus.REQUIRES_APPROVAL.value
    purchase_id = pr_res.json()["id"]

    # Attempt to create order should fail with 400 Bad Request (StateTransitionError)
    fail_res = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx["admin_headers"],
        json={"purchase_request_id": purchase_id},
    )
    assert fail_res.status_code == 400


@pytest.mark.asyncio
async def test_uncertain_outcome_network_timeout_retains_reservation(async_client, db_session):
    """
    Financial Invariant: Network timeouts or uncertain capture outcomes must NOT
    release reserved budget funds, and must NOT mark payment complete.
    Status remains CAPTURE_PENDING.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="TimeoutCorp",
        admin_email="admin@timeoutcorp.io",
        approval_threshold_amount="500.00",
        budget_allocated="2000.00",
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute Cloud Server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    purchase_id = uuid.UUID(pr_res.json()["id"])

    # Create order successfully
    o_res = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx["admin_headers"],
        json={"purchase_request_id": str(purchase_id)},
    )
    order_id = o_res.json()["provider_order_id"]

    # Inject timeout client for capture
    timing_out_client = MockPayPalClient(should_timeout_capture=True)
    set_paypal_client(timing_out_client)

    # Capture attempt will encounter timeout
    cap_res = await async_client.post(
        "/api/v1/payments/capture",
        headers=ctx["admin_headers"],
        json={"provider_order_id": order_id},
    )
    assert cap_res.status_code == 400
    assert "uncertain" in cap_res.text.lower() or "timeout" in cap_res.text.lower()

    # Invariant Verification:
    # 1. PaymentAttempt status is CAPTURE_PENDING
    stmt_att = select(PaymentAttempt).where(PaymentAttempt.provider_order_id == order_id)
    attempt = await db_session.scalar(stmt_att)
    assert attempt.status == PaymentStatus.CAPTURE_PENDING

    # 2. BudgetReservation remains ACTIVE (NOT released, NOT settled!)
    stmt_res = select(BudgetReservation).where(BudgetReservation.purchase_request_id == purchase_id)
    res_record = await db_session.scalar(stmt_res)
    assert res_record.status == ReservationStatus.ACTIVE

    # 3. PurchaseRequest remains AUTHORIZED (not completed)
    stmt_pr = select(PurchaseRequest).where(PurchaseRequest.id == purchase_id)
    pr = await db_session.scalar(stmt_pr)
    assert pr.status == PurchaseStatus.AUTHORIZED

    # 4. No settled transactions
    stmt_tx = select(Transaction).where(Transaction.purchase_request_id == purchase_id)
    tx = await db_session.scalar(stmt_tx)
    assert tx is None


@pytest.mark.asyncio
async def test_definitive_failure_releases_reservation(async_client, db_session):
    """
    On definitive terminal failure (e.g. PayPal DECLINED), the budget reservation
    must be atomically released back to the available pool.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="DeclineCorp",
        admin_email="admin@declinecorp.io",
        approval_threshold_amount="500.00",
        budget_allocated="2000.00",
    )

    pr_res = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute Cloud Server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    purchase_id = uuid.UUID(pr_res.json()["id"])

    o_res = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx["admin_headers"],
        json={"purchase_request_id": str(purchase_id)},
    )
    order_id = o_res.json()["provider_order_id"]

    # Inject declined client
    declining_client = MockPayPalClient(should_fail_capture=True)
    set_paypal_client(declining_client)

    cap_res = await async_client.post(
        "/api/v1/payments/capture",
        headers=ctx["admin_headers"],
        json={"provider_order_id": order_id},
    )
    assert cap_res.status_code == 400

    # Invariant Verification:
    # 1. Attempt is FAILED
    stmt_att = select(PaymentAttempt).where(PaymentAttempt.provider_order_id == order_id)
    attempt = await db_session.scalar(stmt_att)
    assert attempt.status == PaymentStatus.FAILED

    # 2. Reservation is RELEASED
    stmt_res = select(BudgetReservation).where(BudgetReservation.purchase_request_id == purchase_id)
    res_record = await db_session.scalar(stmt_res)
    assert res_record.status == ReservationStatus.RELEASED

    # 3. Purchase is CANCELLED
    stmt_pr = select(PurchaseRequest).where(PurchaseRequest.id == purchase_id)
    pr = await db_session.scalar(stmt_pr)
    assert pr.status == PurchaseStatus.CANCELLED


@pytest.mark.asyncio
async def test_cross_organization_payment_isolation(async_client, db_session):
    """
    Ensure Org B cannot create orders or capture payments for Org A's purchases.
    """
    ctx_a = await setup_org_agent_policy_budget(
        async_client,
        org_name="OrgA-Pay",
        admin_email="admin@orga-pay.io",
        approval_threshold_amount="500.00",
    )
    ctx_b = await setup_org_agent_policy_budget(
        async_client,
        org_name="OrgB-Pay",
        admin_email="admin@orgb-pay.io",
        approval_threshold_amount="500.00",
    )

    # Org A creates purchase & order
    pr_a = await async_client.post(
        "/api/v1/purchases",
        headers=ctx_a["agent_headers"],
        json={
            "item_description": "Compute Cloud Server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    purchase_a_id = pr_a.json()["id"]

    o_a = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx_a["admin_headers"],
        json={"purchase_request_id": purchase_a_id},
    )
    order_a_id = o_a.json()["provider_order_id"]

    # Org B attempts to capture Org A's order -> 404
    cross_cap = await async_client.post(
        "/api/v1/payments/capture",
        headers=ctx_b["admin_headers"],
        json={"provider_order_id": order_a_id},
    )
    assert cross_cap.status_code == 404

    # Org B attempts to create order for Org A's purchase -> 404
    cross_create = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx_b["admin_headers"],
        json={"purchase_request_id": purchase_a_id},
    )
    assert cross_create.status_code == 404


@pytest.mark.asyncio
async def test_get_payment_status(async_client, db_session):
    """
    Test GET /api/v1/payments/{provider_order_id} returns accurate status.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="StatusCorp",
        admin_email="admin@statuscorp.io",
        approval_threshold_amount="500.00",
    )

    pr = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute Cloud Server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    purchase_id = pr.json()["id"]

    o = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx["admin_headers"],
        json={"purchase_request_id": purchase_id},
    )
    order_id = o.json()["provider_order_id"]

    status_res = await async_client.get(
        f"/api/v1/payments/{order_id}",
        headers=ctx["admin_headers"],
    )
    assert status_res.status_code == 200
    st_data = status_res.json()
    assert st_data["provider_order_id"] == order_id
    assert st_data["status"] == PaymentStatus.ORDER_CREATED.value
    assert st_data["approval_url"] is not None


@pytest.mark.asyncio
async def test_paypal_webhook_processing_and_idempotency(async_client, db_session):
    """
    Test PayPal webhook processing:
    1. CHECKOUT.ORDER.APPROVED transitions attempt to BUYER_APPROVAL_PENDING.
    2. PAYMENT.CAPTURE.COMPLETED transitions attempt to COMPLETED, settles reservation, creates transaction.
    3. Replaying the exact same webhook is idempotent (status: already_processed).
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="WebhookCorp",
        admin_email="admin@webhookcorp.io",
        approval_threshold_amount="500.00",
    )

    pr = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Compute Cloud Server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    purchase_id = uuid.UUID(pr.json()["id"])

    o = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx["admin_headers"],
        json={"purchase_request_id": str(purchase_id)},
    )
    order_id = o.json()["provider_order_id"]

    # 1. Simulate CHECKOUT.ORDER.APPROVED webhook
    event_id_1 = f"WH-{uuid.uuid4().hex[:12]}"
    wh_resp_1 = await async_client.post(
        "/api/v1/payments/webhook",
        headers={"x-mock-webhook": "true"},
        json={
            "id": event_id_1,
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "resource": {"id": order_id},
        },
    )
    assert wh_resp_1.status_code == 200
    assert wh_resp_1.json()["status"] == "processed"

    stmt_att = select(PaymentAttempt).where(PaymentAttempt.provider_order_id == order_id)
    attempt = await db_session.scalar(stmt_att)
    assert attempt.status == PaymentStatus.BUYER_APPROVAL_PENDING

    # 2. Simulate PAYMENT.CAPTURE.COMPLETED webhook
    event_id_2 = f"WH-{uuid.uuid4().hex[:12]}"
    capture_id = f"CAP-WH-{uuid.uuid4().hex[:8]}"
    wh_resp_2 = await async_client.post(
        "/api/v1/payments/webhook",
        headers={"x-mock-webhook": "true"},
        json={
            "id": event_id_2,
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {
                "id": capture_id,
                "supplementary_data": {"related_ids": {"order_id": order_id}},
            },
        },
    )
    assert wh_resp_2.status_code == 200
    assert wh_resp_2.json()["status"] == "processed"

    await db_session.refresh(attempt)
    assert attempt.status == PaymentStatus.COMPLETED
    assert attempt.provider_capture_id == capture_id

    stmt_res = select(BudgetReservation).where(BudgetReservation.purchase_request_id == purchase_id)
    res_record = await db_session.scalar(stmt_res)
    assert res_record.status == ReservationStatus.SETTLED

    stmt_pr = select(PurchaseRequest).where(PurchaseRequest.id == purchase_id)
    pr_record = await db_session.scalar(stmt_pr)
    assert pr_record.status == PurchaseStatus.COMPLETED

    # 3. Replay duplicate webhook (idempotency check)
    dup_resp = await async_client.post(
        "/api/v1/payments/webhook",
        headers={"x-mock-webhook": "true"},
        json={
            "id": event_id_2,
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {
                "id": capture_id,
                "supplementary_data": {"related_ids": {"order_id": order_id}},
            },
        },
    )
    assert dup_resp.status_code == 200
    assert dup_resp.json()["status"] == "already_processed"

