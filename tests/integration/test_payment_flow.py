import decimal
import uuid
import pytest
from app.core.constants import PurchaseStatus, PaymentStatus, ReservationStatus, TransactionStatus, TransactionType
from app.models.budget import Budget
from app.models.purchase import PurchaseRequest
from app.models.supplier import SupplierQuote, Supplier


@pytest.mark.asyncio
async def test_payment_creation_capture_and_reconciliation(async_client):
    # 1. Register Admin & Org
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={
            "email": "payadmin@fintech.io",
            "password": "Password123!",
            "full_name": "Payment Admin",
            "organization_name": "Fintech Corp",
        },
    )
    admin_token = reg_res.json()["access_token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    # 2. Create Agent
    agent_res = await async_client.post(
        "/api/v1/agents",
        headers=admin_headers,
        json={"name": "BuyerAgent"},
    )
    agent_id = agent_res.json()["agent"]["id"]
    agent_headers = {"X-Agent-API-Key": agent_res.json()["credentials"]["raw_api_key"]}

    # 3. Create Budget ($5000)
    await async_client.post(
        "/api/v1/budgets",
        headers=admin_headers,
        json={"name": "Ops Budget", "allocated_amount": "5000.00", "currency": "USD"},
    )

    # 4. Create Policy ($1000 limit, $500 threshold)
    p_res = await async_client.post(
        "/api/v1/policies",
        headers=admin_headers,
        json={
            "name": "General Spend",
            "max_amount_per_transaction": "1000.00",
            "max_amount_per_day": "3000.00",
            "approval_threshold_amount": "500.00",
            "allowed_suppliers": ["mock_supplier_a", "mock_supplier_b"],
            "allowed_currencies": ["USD"],
        },
    )
    policy_id = p_res.json()["id"]
    await async_client.post(
        f"/api/v1/policies/assignments/{agent_id}",
        headers=admin_headers,
        json={"policy_id": policy_id},
    )

    # 5. Agent requests purchase ($120 < $500 threshold, so status=AUTHORIZED directly)
    p_req = await async_client.post(
        "/api/v1/purchases",
        headers=agent_headers,
        json={
            "item_description": "Server compute instance",
            "category": "compute",
            "max_budget": "200.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    assert p_req.status_code == 201
    purchase_data = p_req.json()
    assert purchase_data["status"] == PurchaseStatus.AUTHORIZED.value
    purchase_id = purchase_data["id"]

    # 6. Create Payment Order
    create_order_res = await async_client.post(
        "/api/v1/payments/create-order",
        headers=admin_headers,
        json={"purchase_request_id": purchase_id},
    )
    assert create_order_res.status_code == 201
    order_data = create_order_res.json()
    assert order_data["status"] == PaymentStatus.ORDER_CREATED.value
    provider_order_id = order_data["provider_order_id"]
    assert "paypal.com" in order_data["approval_url"]

    # 7. Capture Payment
    capture_res = await async_client.post(
        "/api/v1/payments/capture",
        headers=admin_headers,
        json={"provider_order_id": provider_order_id},
    )
    assert capture_res.status_code == 200
    capture_data = capture_res.json()
    assert capture_data["status"] == PaymentStatus.COMPLETED.value
    assert capture_data["provider_capture_id"] is not None

    # 8. Verify Purchase status is now COMPLETED
    p_check = await async_client.get(f"/api/v1/purchases/{purchase_id}", headers=admin_headers)
    assert p_check.status_code == 200
    assert p_check.json()["status"] == PurchaseStatus.COMPLETED.value

    # 9. Verify Ledger Transactions & Reconciliation
    tx_res = await async_client.get("/api/v1/transactions", headers=admin_headers)
    assert tx_res.status_code == 200
    txs = tx_res.json()
    assert len(txs) == 1
    assert txs[0]["status"] == TransactionStatus.SETTLED.value
    assert txs[0]["amount"] == "120.00"

    reconcile_res = await async_client.get("/api/v1/transactions/reconcile", headers=admin_headers)
    assert reconcile_res.status_code == 200
    rec_data = reconcile_res.json()
    assert rec_data["settled_count"] == 1
    assert rec_data["total_spent_amount"] == "120.00"


@pytest.mark.asyncio
async def test_paypal_webhook_idempotency(async_client):
    event_id = f"WH-TEST-{uuid.uuid4().hex[:12]}"
    webhook_payload = {
        "id": event_id,
        "event_type": "CHECKOUT.ORDER.APPROVED",
        "resource": {"id": "ORDER-MOCK-TEST-123"},
    }
    headers = {"x-mock-webhook": "true", "Content-Type": "application/json"}

    # First delivery
    res1 = await async_client.post("/api/v1/webhooks/paypal", json=webhook_payload, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["status"] == "processed"

    # Second delivery (Duplicate event)
    res2 = await async_client.post("/api/v1/webhooks/paypal", json=webhook_payload, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["status"] == "already_processed"
