import decimal
import uuid
import pytest
from sqlalchemy import select

from app.core.constants import (
    AuditAction,
    FulfillmentStatus,
    PaymentStatus,
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
from app.models.audit import AuditEvent
from app.models.budget import Budget, BudgetReservation
from app.models.payment import PaymentAttempt
from app.models.purchase import PurchaseRequest
from app.models.transaction import Transaction
from app.models.webhook import WebhookEvent
from tests.integration.test_procurement_milestone3 import setup_org_agent_policy_budget


@pytest.fixture(autouse=True)
def restore_paypal_client():
    """Ensure paypal client is restored to default after each test."""
    original = get_paypal_client()
    yield
    set_paypal_client(original)


async def create_authorized_purchase_and_order(async_client, ctx: dict) -> tuple[uuid.UUID, str, decimal.Decimal]:
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
    pr_data = pr_res.json()
    purchase_id = uuid.UUID(pr_data["id"])

    o_res = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx["admin_headers"],
        json={"purchase_request_id": str(purchase_id)},
    )
    assert o_res.status_code == 201
    order_data = o_res.json()
    provider_order_id = order_data["provider_order_id"]
    amount = decimal.Decimal(str(order_data["amount"]))
    return purchase_id, provider_order_id, amount


@pytest.mark.asyncio
async def test_webhook_signature_verification_and_header_enforcement(async_client):
    """
    Verify webhook signature validation:
    1. Missing headers -> 400 Bad Request
    2. Invalid mock signature -> 400 Bad Request
    3. Valid mock signature -> 200 OK
    """
    # 1. Missing required headers without mock bypass
    res_missing = await async_client.post(
        "/api/v1/payments/webhook",
        headers={},
        json={"id": "WH-MISSING-1", "event_type": "CHECKOUT.ORDER.APPROVED"},
    )
    assert res_missing.status_code == 400
    assert "Missing required PayPal verification headers" in res_missing.text

    # 2. Invalid mock signature
    res_invalid_sig = await async_client.post(
        "/api/v1/payments/webhook",
        headers={
            "paypal-transmission-id": "trans-123",
            "paypal-transmission-time": "2026-11-10T21:00:00Z",
            "paypal-cert-url": "https://api.paypal.com/cert",
            "paypal-auth-algo": "SHA256withRSA",
            "paypal-transmission-sig": "INVALID_SIGNATURE_TAMPERED",
        },
        json={"id": "WH-INVALID-SIG-1", "event_type": "CHECKOUT.ORDER.APPROVED"},
    )
    assert res_invalid_sig.status_code == 400
    assert "signature" in res_invalid_sig.text.lower()

    # 3. Valid simulated signature
    res_valid = await async_client.post(
        "/api/v1/payments/webhook",
        headers={
            "paypal-transmission-id": "trans-123",
            "paypal-transmission-time": "2026-11-10T21:00:00Z",
            "paypal-cert-url": "https://api.paypal.com/cert",
            "paypal-auth-algo": "SHA256withRSA",
            "paypal-transmission-sig": "VALID_MOCK_SIGNATURE_TOKEN",
        },
        json={"id": "WH-VALID-1", "event_type": "CHECKOUT.ORDER.APPROVED", "resource": {}},
    )
    assert res_valid.status_code == 200
    assert res_valid.json()["status"] == "processed"


@pytest.mark.asyncio
async def test_webhook_idempotency_and_duplicate_event_rejection(async_client, db_session):
    """
    Enforce unique provider event IDs and idempotency.
    Replaying the exact same event must return 'already_processed' without duplicate mutations.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="IdemWebCorp",
        admin_email="admin@idemwebcorp.io",
        approval_threshold_amount="500.00",
    )
    purchase_id, order_id, amount = await create_authorized_purchase_and_order(async_client, ctx)

    event_id = f"WH-IDEM-{uuid.uuid4().hex[:8]}"
    capture_id = f"CAP-IDEM-{uuid.uuid4().hex[:8]}"
    wh_payload = {
        "id": event_id,
        "event_type": "PAYMENT.CAPTURE.COMPLETED",
        "resource": {
            "id": capture_id,
            "supplementary_data": {"related_ids": {"order_id": order_id}},
        },
    }

    # 1. First delivery
    res_1 = await async_client.post(
        "/api/v1/payments/webhook",
        headers={"x-mock-webhook": "true"},
        json=wh_payload,
    )
    assert res_1.status_code == 200
    assert res_1.json()["status"] == "processed"

    # Verify transaction created
    stmt_tx = select(Transaction).where(Transaction.purchase_request_id == purchase_id)
    txs = (await db_session.scalars(stmt_tx)).all()
    assert len(txs) == 1

    # 2. Duplicate replay delivery
    res_2 = await async_client.post(
        "/api/v1/payments/webhook",
        headers={"x-mock-webhook": "true"},
        json=wh_payload,
    )
    assert res_2.status_code == 200
    assert res_2.json()["status"] == "already_processed"

    # Verify still exactly 1 transaction and 1 webhook_events row
    txs_after = (await db_session.scalars(stmt_tx)).all()
    assert len(txs_after) == 1

    stmt_wh = select(WebhookEvent).where(WebhookEvent.provider_event_id == event_id)
    wh_records = (await db_session.scalars(stmt_wh)).all()
    assert len(wh_records) == 1


@pytest.mark.asyncio
async def test_webhook_capture_pending_retains_budget_reservation(async_client, db_session):
    """
    PAYMENT.CAPTURE.PENDING event (e.g. eCheck clearing or risk review):
    Attempt status -> CAPTURE_PENDING.
    Reservation status -> ACTIVE (retained, NOT released, NOT settled!).
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="PendingCorp",
        admin_email="admin@pendingcorp.io",
        approval_threshold_amount="500.00",
    )
    purchase_id, order_id, amount = await create_authorized_purchase_and_order(async_client, ctx)

    capture_id = f"CAP-PEND-{uuid.uuid4().hex[:8]}"
    wh_res = await async_client.post(
        "/api/v1/payments/webhook",
        headers={"x-mock-webhook": "true"},
        json={
            "id": f"WH-PEND-{uuid.uuid4().hex[:8]}",
            "event_type": "PAYMENT.CAPTURE.PENDING",
            "resource": {
                "id": capture_id,
                "supplementary_data": {"related_ids": {"order_id": order_id}},
            },
        },
    )
    assert wh_res.status_code == 200

    # Invariants verification:
    stmt_att = select(PaymentAttempt).where(PaymentAttempt.provider_order_id == order_id)
    att = await db_session.scalar(stmt_att)
    assert att.status == PaymentStatus.CAPTURE_PENDING

    stmt_res = select(BudgetReservation).where(BudgetReservation.purchase_request_id == purchase_id)
    res_record = await db_session.scalar(stmt_res)
    assert res_record.status == ReservationStatus.ACTIVE

    stmt_pr = select(PurchaseRequest).where(PurchaseRequest.id == purchase_id)
    pr = await db_session.scalar(stmt_pr)
    assert pr.status == PurchaseStatus.AUTHORIZED
    assert pr.fulfillment_status == FulfillmentStatus.NOT_STARTED


@pytest.mark.asyncio
async def test_webhook_capture_denied_releases_budget_and_cancels_purchase(async_client, db_session):
    """
    PAYMENT.CAPTURE.DENIED event:
    Attempt status -> FAILED.
    Reservation status -> RELEASED (funds returned to budget pool).
    PurchaseRequest status -> CANCELLED, fulfillment_status -> FAILED.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="DeniedCorp",
        admin_email="admin@deniedcorp.io",
        approval_threshold_amount="500.00",
    )
    purchase_id, order_id, amount = await create_authorized_purchase_and_order(async_client, ctx)

    wh_res = await async_client.post(
        "/api/v1/payments/webhook",
        headers={"x-mock-webhook": "true"},
        json={
            "id": f"WH-DENIED-{uuid.uuid4().hex[:8]}",
            "event_type": "PAYMENT.CAPTURE.DENIED",
            "resource": {
                "id": f"CAP-DENIED-{uuid.uuid4().hex[:8]}",
                "supplementary_data": {"related_ids": {"order_id": order_id}},
            },
        },
    )
    assert wh_res.status_code == 200

    # Invariants verification:
    stmt_att = select(PaymentAttempt).where(PaymentAttempt.provider_order_id == order_id)
    att = await db_session.scalar(stmt_att)
    assert att.status == PaymentStatus.FAILED

    stmt_res = select(BudgetReservation).where(BudgetReservation.purchase_request_id == purchase_id)
    res_record = await db_session.scalar(stmt_res)
    assert res_record.status == ReservationStatus.RELEASED

    stmt_pr = select(PurchaseRequest).where(PurchaseRequest.id == purchase_id)
    pr = await db_session.scalar(stmt_pr)
    assert pr.status == PurchaseStatus.CANCELLED
    assert pr.fulfillment_status == FulfillmentStatus.FAILED


@pytest.mark.asyncio
async def test_webhook_capture_refunded_records_refund_and_recredits_budget(async_client, db_session):
    """
    PAYMENT.CAPTURE.REFUNDED event:
    1. Complete payment via capture.
    2. Deliver refund webhook referencing parent capture ID.
    3. New Transaction(type=REFUND) is appended without mutating original.
    4. Budget spent_amount is decremented.
    5. PaymentAttempt status -> REFUNDED.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="RefundCorp",
        admin_email="admin@refundcorp.io",
        approval_threshold_amount="500.00",
        budget_allocated="5000.00",
    )
    purchase_id, order_id, amount = await create_authorized_purchase_and_order(async_client, ctx)

    # 1. Complete capture
    cap_res = await async_client.post(
        "/api/v1/payments/capture",
        headers=ctx["admin_headers"],
        json={"provider_order_id": order_id},
    )
    assert cap_res.status_code == 200
    capture_id = cap_res.json()["provider_capture_id"]

    stmt_b = select(Budget).where(Budget.id == uuid.UUID(ctx["budget_id"]))
    budget_before_refund = await db_session.scalar(stmt_b)
    assert budget_before_refund.spent_amount == amount

    # 2. Deliver refund webhook
    refund_id = f"REF-{uuid.uuid4().hex[:8]}"
    wh_res = await async_client.post(
        "/api/v1/payments/webhook",
        headers={"x-mock-webhook": "true"},
        json={
            "id": f"WH-REF-{uuid.uuid4().hex[:8]}",
            "event_type": "PAYMENT.CAPTURE.REFUNDED",
            "resource": {
                "id": refund_id,
                "amount": {"value": str(amount), "currency_code": "USD"},
                "links": [{"href": f"https://api.paypal.com/v2/payments/captures/{capture_id}", "rel": "up"}],
            },
        },
    )
    assert wh_res.status_code == 200

    # 3. Verify ledger & budget
    stmt_txs = select(Transaction).where(Transaction.purchase_request_id == purchase_id)
    txs = (await db_session.scalars(stmt_txs)).all()
    assert len(txs) == 2

    purchase_tx = next(t for t in txs if t.type == TransactionType.PURCHASE)
    refund_tx = next(t for t in txs if t.type == TransactionType.REFUND)

    assert purchase_tx.status == TransactionStatus.SETTLED
    assert refund_tx.status == TransactionStatus.REFUNDED
    assert refund_tx.amount == amount
    assert refund_tx.provider_transaction_id == refund_id

    await db_session.refresh(budget_before_refund)
    assert budget_before_refund.spent_amount == decimal.Decimal("0.00")

    stmt_att = select(PaymentAttempt).where(PaymentAttempt.provider_order_id == order_id)
    att = await db_session.scalar(stmt_att)
    assert att.status == PaymentStatus.REFUNDED


@pytest.mark.asyncio
async def test_out_of_order_and_delayed_events(async_client, db_session):
    """
    Test resiliency to delayed and out-of-order events:
    1. PAYMENT.CAPTURE.COMPLETED arrives first (order transitions directly to COMPLETED).
    2. CHECKOUT.ORDER.APPROVED arrives later (must NOT regress to BUYER_APPROVAL_PENDING).
    3. PAYMENT.CAPTURE.DENIED arrives after completion (must NOT regress to FAILED or release settled funds).
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="OrderCorp",
        admin_email="admin@ordercorp.io",
        approval_threshold_amount="500.00",
    )
    purchase_id, order_id, amount = await create_authorized_purchase_and_order(async_client, ctx)

    capture_id = f"CAP-OOO-{uuid.uuid4().hex[:8]}"

    # Step 1: Capture completed arrives out-of-order
    await async_client.post(
        "/api/v1/payments/webhook",
        headers={"x-mock-webhook": "true"},
        json={
            "id": f"WH-OOO-1-{uuid.uuid4().hex[:8]}",
            "event_type": "PAYMENT.CAPTURE.COMPLETED",
            "resource": {
                "id": capture_id,
                "supplementary_data": {"related_ids": {"order_id": order_id}},
            },
        },
    )
    stmt_att = select(PaymentAttempt).where(PaymentAttempt.provider_order_id == order_id)
    att = await db_session.scalar(stmt_att)
    assert att.status == PaymentStatus.COMPLETED

    # Step 2: Delayed CHECKOUT.ORDER.APPROVED arrives
    await async_client.post(
        "/api/v1/payments/webhook",
        headers={"x-mock-webhook": "true"},
        json={
            "id": f"WH-OOO-2-{uuid.uuid4().hex[:8]}",
            "event_type": "CHECKOUT.ORDER.APPROVED",
            "resource": {"id": order_id},
        },
    )
    await db_session.refresh(att)
    # Must NOT regress to BUYER_APPROVAL_PENDING
    assert att.status == PaymentStatus.COMPLETED

    # Step 3: Delayed/bogus denial arrives after completed
    await async_client.post(
        "/api/v1/payments/webhook",
        headers={"x-mock-webhook": "true"},
        json={
            "id": f"WH-OOO-3-{uuid.uuid4().hex[:8]}",
            "event_type": "PAYMENT.CAPTURE.DENIED",
            "resource": {
                "id": capture_id,
                "supplementary_data": {"related_ids": {"order_id": order_id}},
            },
        },
    )
    await db_session.refresh(att)
    # Must remain COMPLETED
    assert att.status == PaymentStatus.COMPLETED


@pytest.mark.asyncio
async def test_reconciliation_authoritative_completed(async_client, db_session):
    """
    Reconcile an uncertain payment attempt (e.g. CAPTURE_PENDING after timeout)
    against PayPal's authoritative API when PayPal indicates COMPLETED.
    Budget reservation must settle, Transaction must be recorded, purchase COMPLETED.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="ReconCorp",
        admin_email="admin@reconcorp.io",
        approval_threshold_amount="500.00",
    )
    purchase_id, order_id, amount = await create_authorized_purchase_and_order(async_client, ctx)

    # 1. Trigger network timeout during capture -> attempt is CAPTURE_PENDING
    timeout_client = MockPayPalClient(should_timeout_capture=True)
    set_paypal_client(timeout_client)

    await async_client.post(
        "/api/v1/payments/capture",
        headers=ctx["admin_headers"],
        json={"provider_order_id": order_id},
    )

    stmt_att = select(PaymentAttempt).where(PaymentAttempt.provider_order_id == order_id)
    att = await db_session.scalar(stmt_att)
    assert att.status == PaymentStatus.CAPTURE_PENDING

    # 2. Configure mock authoritative API to report COMPLETED
    recon_capture_id = f"CAP-RECON-SUCCESS-{uuid.uuid4().hex[:8]}"
    mock_authoritative = MockPayPalClient()
    mock_authoritative.set_mock_order(
        order_id=order_id,
        status="COMPLETED",
        capture_id=recon_capture_id,
        capture_status="COMPLETED",
        amount=str(amount),
    )
    set_paypal_client(mock_authoritative)

    # 3. Call reconciliation endpoint
    recon_res = await async_client.post(
        f"/api/v1/payments/{order_id}/reconcile",
        headers=ctx["admin_headers"],
    )
    assert recon_res.status_code == 200
    res_data = recon_res.json()
    assert res_data["status"] == PaymentStatus.COMPLETED.value
    assert res_data["provider_capture_id"] == recon_capture_id

    # 4. Verify post-conditions
    await db_session.refresh(att)
    assert att.status == PaymentStatus.COMPLETED
    assert att.provider_capture_id == recon_capture_id

    stmt_res = select(BudgetReservation).where(BudgetReservation.purchase_request_id == purchase_id)
    res_record = await db_session.scalar(stmt_res)
    assert res_record.status == ReservationStatus.SETTLED

    stmt_pr = select(PurchaseRequest).where(PurchaseRequest.id == purchase_id)
    pr = await db_session.scalar(stmt_pr)
    assert pr.status == PurchaseStatus.COMPLETED
    assert pr.fulfillment_status == FulfillmentStatus.PENDING

    stmt_tx = select(Transaction).where(Transaction.purchase_request_id == purchase_id)
    tx = await db_session.scalar(stmt_tx)
    assert tx is not None
    assert tx.status == TransactionStatus.SETTLED
    assert tx.amount == amount


@pytest.mark.asyncio
async def test_reconciliation_authoritative_voided_or_failed(async_client, db_session):
    """
    Reconcile an uncertain payment attempt against PayPal's authoritative API
    when PayPal indicates VOIDED / EXPIRED / FAILED.
    Budget reservation must be released, attempt FAILED, purchase CANCELLED.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="VoidReconCorp",
        admin_email="admin@voidreconcorp.io",
        approval_threshold_amount="500.00",
    )
    purchase_id, order_id, amount = await create_authorized_purchase_and_order(async_client, ctx)

    # 1. Trigger timeout -> CAPTURE_PENDING
    timeout_client = MockPayPalClient(should_timeout_capture=True)
    set_paypal_client(timeout_client)

    await async_client.post(
        "/api/v1/payments/capture",
        headers=ctx["admin_headers"],
        json={"provider_order_id": order_id},
    )

    # 2. Configure mock authoritative API to report VOIDED
    mock_authoritative = MockPayPalClient()
    mock_authoritative.set_mock_order(
        order_id=order_id,
        status="VOIDED",
    )
    set_paypal_client(mock_authoritative)

    # 3. Call reconciliation endpoint
    recon_res = await async_client.post(
        f"/api/v1/payments/{order_id}/reconcile",
        headers=ctx["admin_headers"],
    )
    assert recon_res.status_code == 200
    assert recon_res.json()["status"] == PaymentStatus.FAILED.value

    # 4. Verify post-conditions
    stmt_att = select(PaymentAttempt).where(PaymentAttempt.provider_order_id == order_id)
    att = await db_session.scalar(stmt_att)
    assert att.status == PaymentStatus.FAILED

    stmt_res = select(BudgetReservation).where(BudgetReservation.purchase_request_id == purchase_id)
    res_record = await db_session.scalar(stmt_res)
    assert res_record.status == ReservationStatus.RELEASED

    stmt_pr = select(PurchaseRequest).where(PurchaseRequest.id == purchase_id)
    pr = await db_session.scalar(stmt_pr)
    assert pr.status == PurchaseStatus.CANCELLED
    assert pr.fulfillment_status == FulfillmentStatus.FAILED


@pytest.mark.asyncio
async def test_bulk_reconciliation_endpoint(async_client, db_session):
    """
    Test POST /api/v1/payments/reconcile reconciles all in-flight orders for organization.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="BulkReconCorp",
        admin_email="admin@bulkreconcorp.io",
        approval_threshold_amount="500.00",
    )
    p1, o1, a1 = await create_authorized_purchase_and_order(async_client, ctx)
    p2, o2, a2 = await create_authorized_purchase_and_order(async_client, ctx)

    # Set up mock authoritative client
    mock_auth = MockPayPalClient(default_order_status="COMPLETED")
    set_paypal_client(mock_auth)

    bulk_res = await async_client.post(
        "/api/v1/payments/reconcile",
        headers=ctx["admin_headers"],
    )
    assert bulk_res.status_code == 200
    results = bulk_res.json()
    assert len(results) >= 2
    order_ids = [r["provider_order_id"] for r in results]
    assert o1 in order_ids
    assert o2 in order_ids
