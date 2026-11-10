import decimal
import uuid
import pytest

from app.core.constants import PurchaseStatus, TransactionStatus, TransactionType
from tests.integration.test_procurement_milestone3 import setup_org_agent_policy_budget


@pytest.mark.asyncio
async def test_frontend_dashboard_and_summaries(async_client, db_session):
    """
    Test frontend dashboard endpoints:
    1. GET /api/v1/dashboard/overview
    2. GET /api/v1/dashboard/stats
    3. GET /api/v1/dashboard/spending
    4. GET /api/v1/dashboard/agents
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="FrontendCorp",
        admin_email="admin@frontendcorp.io",
        approval_threshold_amount="500.00",
        budget_allocated="5000.00",
    )

    # 1. Initially check dashboard stats
    stats_res = await async_client.get("/api/v1/dashboard/stats", headers=ctx["admin_headers"])
    assert stats_res.status_code == 200
    st = stats_res.json()
    assert st["total_agents"] == 1
    assert st["active_agents"] == 1
    assert decimal.Decimal(st["total_budget_allocated"]) == decimal.Decimal("5000.00")
    assert decimal.Decimal(st["total_budget_spent"]) == decimal.Decimal("0.00")

    # 2. Agent submits purchase and it is captured to produce transactions and spending
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
    purchase_id = pr_res.json()["id"]

    o_res = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx["admin_headers"],
        json={"purchase_request_id": purchase_id},
    )
    assert o_res.status_code == 201
    order_id = o_res.json()["provider_order_id"]

    cap_res = await async_client.post(
        "/api/v1/payments/capture",
        headers=ctx["admin_headers"],
        json={"provider_order_id": order_id},
    )
    assert cap_res.status_code == 200
    captured_amount = decimal.Decimal(str(cap_res.json()["amount"]))

    # 3. Verify Dashboard Overview
    overview_res = await async_client.get("/api/v1/dashboard/overview", headers=ctx["admin_headers"])
    assert overview_res.status_code == 200
    ov_data = overview_res.json()
    assert "stats" in ov_data
    assert "recent_activities" in ov_data
    assert ov_data["stats"]["completed_purchases_count"] == 1
    assert len(ov_data["recent_activities"]) >= 1

    # 4. Verify Spending Summary
    spend_res = await async_client.get("/api/v1/dashboard/spending", headers=ctx["admin_headers"])
    assert spend_res.status_code == 200
    spend_data = spend_res.json()
    assert decimal.Decimal(str(spend_data["total_spent"])) == captured_amount
    assert "compute" in spend_data["by_category"]
    assert decimal.Decimal(str(spend_data["by_category"]["compute"])) == captured_amount
    assert len(spend_data["by_agent"]) == 1
    assert spend_data["by_agent"][0]["agent_name"] == "AutoProcure-Bot"

    # 5. Verify Agent Summaries
    agents_res = await async_client.get("/api/v1/dashboard/agents", headers=ctx["admin_headers"])
    assert agents_res.status_code == 200
    ag_list = agents_res.json()
    assert len(ag_list) == 1
    ag = ag_list[0]
    assert ag["name"] == "AutoProcure-Bot"
    assert ag["is_active"] is True
    assert ag["assigned_policy_name"] == "Standard Spend Policy"
    assert ag["total_purchases_completed"] == 1
    assert decimal.Decimal(str(ag["total_spent"])) == captured_amount


@pytest.mark.asyncio
async def test_frontend_transactions_paginated_listing_filtering_and_sorting(async_client, db_session):
    """
    Test transaction listing with pagination, filters, and sorting.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="TxListCorp",
        admin_email="admin@txlistcorp.io",
        approval_threshold_amount="500.00",
        budget_allocated="5000.00",
    )

    # Create and capture two separate purchases
    for item_desc in ["Compute Cluster Alpha", "Compute Cluster Beta"]:
        pr = await async_client.post(
            "/api/v1/purchases",
            headers=ctx["agent_headers"],
            json={
                "item_description": item_desc,
                "category": "compute",
                "max_budget": "300.00",
                "currency": "USD",
                "requirements": {"quantity": 1},
            },
        )
        pid = pr.json()["id"]
        order = await async_client.post(
            "/api/v1/payments/create-order",
            headers=ctx["admin_headers"],
            json={"purchase_request_id": pid},
        )
        oid = order.json()["provider_order_id"]
        await async_client.post(
            "/api/v1/payments/capture",
            headers=ctx["admin_headers"],
            json={"provider_order_id": oid},
        )

    # 1. Test Paginated Response Structure
    res = await async_client.get(
        "/api/v1/transactions?page=1&page_size=1",
        headers=ctx["admin_headers"],
    )
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert "total" in data
    assert "page" in data
    assert "page_size" in data
    assert "total_pages" in data
    assert data["page"] == 1
    assert data["page_size"] == 1
    assert data["total"] == 2
    assert data["total_pages"] == 2
    assert len(data["items"]) == 1

    # 2. Test Filtering by Status and Type
    filter_res = await async_client.get(
        "/api/v1/transactions?status=SETTLED&type=PURCHASE",
        headers=ctx["admin_headers"],
    )
    assert filter_res.status_code == 200
    assert filter_res.json()["total"] == 2

    empty_res = await async_client.get(
        "/api/v1/transactions?type=REFUND",
        headers=ctx["admin_headers"],
    )
    assert empty_res.status_code == 200
    assert empty_res.json()["total"] == 0

    # 3. Test Sorting
    sort_res = await async_client.get(
        "/api/v1/transactions?sort_by=created_at&sort_order=asc",
        headers=ctx["admin_headers"],
    )
    assert sort_res.status_code == 200
    items = sort_res.json()["items"]
    assert len(items) == 2
    assert items[0]["created_at"] <= items[1]["created_at"]


@pytest.mark.asyncio
async def test_frontend_transaction_detail_timeline_and_receipt(async_client, db_session):
    """
    Test transaction detail, lifecycle timeline, and digital receipt generation.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="ReceiptCorp",
        admin_email="admin@receiptcorp.io",
        approval_threshold_amount="500.00",
        budget_allocated="5000.00",
    )

    pr = await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Production GPU Cluster",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    pid = pr.json()["id"]

    order = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx["admin_headers"],
        json={"purchase_request_id": pid},
    )
    oid = order.json()["provider_order_id"]

    cap = await async_client.post(
        "/api/v1/payments/capture",
        headers=ctx["admin_headers"],
        json={"provider_order_id": oid},
    )
    tx_id = cap.json()["transaction_id"]

    # 1. Transaction Detail
    det_res = await async_client.get(
        f"/api/v1/transactions/{tx_id}",
        headers=ctx["admin_headers"],
    )
    assert det_res.status_code == 200
    det = det_res.json()
    assert det["id"] == tx_id
    assert det["status"] == TransactionStatus.SETTLED.value
    assert det["purchase_request"] is not None
    assert det["purchase_request"]["item_description"] == "Production GPU Cluster"
    assert det["payment_attempt"] is not None
    assert det["payment_attempt"]["provider_order_id"] == oid

    # 2. Transaction Timeline
    time_res = await async_client.get(
        f"/api/v1/transactions/{tx_id}/timeline",
        headers=ctx["admin_headers"],
    )
    assert time_res.status_code == 200
    time_data = time_res.json()
    assert time_data["transaction_id"] == tx_id
    assert time_data["purchase_request_id"] == pid
    events = time_data["events"]
    assert len(events) >= 2
    actions = [e["action"] for e in events]
    assert "PURCHASE_REQUESTED" in actions
    assert "PAYMENT_CAPTURED" in actions

    # 3. Transaction Receipt
    rec_res = await async_client.get(
        f"/api/v1/transactions/{tx_id}/receipt",
        headers=ctx["admin_headers"],
    )
    assert rec_res.status_code == 200
    rec = rec_res.json()
    assert rec["receipt_number"].startswith("REC-AEON-")
    assert rec["organization_name"] == "ReceiptCorp"
    assert rec["item_description"] == "Production GPU Cluster"
    assert rec["agent_name"] == "AutoProcure-Bot"
    assert rec["payment_method"] == "PayPal Orders v2 (CAPTURE)"
    assert rec["provider_capture_id"] is not None


@pytest.mark.asyncio
async def test_frontend_audit_trail_paginated_listing_and_filtering(async_client, db_session):
    """
    Test organization audit trail query endpoint with pagination, action filters, and sorting.
    """
    ctx = await setup_org_agent_policy_budget(
        async_client,
        org_name="AuditTrailCorp",
        admin_email="admin@audittrailcorp.io",
        approval_threshold_amount="500.00",
    )

    # Submit a purchase to generate procurement audit events
    await async_client.post(
        "/api/v1/purchases",
        headers=ctx["agent_headers"],
        json={
            "item_description": "Audit Test Server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )

    # Check audit events endpoint
    audit_res = await async_client.get(
        "/api/v1/audit?page=1&page_size=10",
        headers=ctx["admin_headers"],
    )
    assert audit_res.status_code == 200
    aud_data = audit_res.json()
    assert "items" in aud_data
    assert "total" in aud_data
    assert aud_data["page"] == 1
    assert aud_data["total"] >= 1

    # Filter by action
    filtered = await async_client.get(
        "/api/v1/audit?action=POLICY_EVALUATED",
        headers=ctx["admin_headers"],
    )
    assert filtered.status_code == 200
    assert filtered.json()["total"] >= 1
    for ev in filtered.json()["items"]:
        assert ev["action"] == "POLICY_EVALUATED"


@pytest.mark.asyncio
async def test_frontend_cross_org_isolation_and_error_envelope(async_client, db_session):
    """
    Verify cross-org resource isolation and standardized error envelopes.
    """
    ctx_a = await setup_org_agent_policy_budget(
        async_client,
        org_name="OrgA-FE",
        admin_email="admin@orga-fe.io",
    )
    ctx_b = await setup_org_agent_policy_budget(
        async_client,
        org_name="OrgB-FE",
        admin_email="admin@orgb-fe.io",
    )

    # Org A creates a purchase and transaction
    pr = await async_client.post(
        "/api/v1/purchases",
        headers=ctx_a["agent_headers"],
        json={
            "item_description": "Org A Server",
            "category": "compute",
            "max_budget": "300.00",
            "currency": "USD",
            "requirements": {"quantity": 1},
        },
    )
    pid = pr.json()["id"]
    order = await async_client.post(
        "/api/v1/payments/create-order",
        headers=ctx_a["admin_headers"],
        json={"purchase_request_id": pid},
    )
    cap = await async_client.post(
        "/api/v1/payments/capture",
        headers=ctx_a["admin_headers"],
        json={"provider_order_id": order.json()["provider_order_id"]},
    )
    tx_a_id = cap.json()["transaction_id"]

    # Org B attempts to access Org A's transaction detail -> 404
    b_det = await async_client.get(
        f"/api/v1/transactions/{tx_a_id}",
        headers=ctx_b["admin_headers"],
    )
    assert b_det.status_code == 404
    err_body = b_det.json()
    assert "error" in err_body
    assert err_body["error"]["code"] == "RESOURCE_NOT_FOUND"

    # Org B attempts to access Org A's receipt -> 404
    b_rec = await async_client.get(
        f"/api/v1/transactions/{tx_a_id}/receipt",
        headers=ctx_b["admin_headers"],
    )
    assert b_rec.status_code == 404

    # Org B attempts to access Org A's timeline -> 404
    b_time = await async_client.get(
        f"/api/v1/transactions/{tx_a_id}/timeline",
        headers=ctx_b["admin_headers"],
    )
    assert b_time.status_code == 404
