import decimal
import datetime
import uuid
import pytest
from sqlalchemy import select
from app.models import (
    Organization,
    User,
    Membership,
    Agent,
    AgentCredential,
    Policy,
    PolicyVersion,
    AgentPolicyAssignment,
    Budget,
    BudgetReservation,
    Supplier,
    SupplierQuote,
    PurchaseRequest,
    Recommendation,
    Approval,
    Transaction,
    PaymentAttempt,
    WebhookEvent,
    AuditEvent,
)
from app.core.constants import UserRole, PurchaseStatus, PaymentStatus, ReservationStatus, TransactionStatus, TransactionType, ApprovalStatus


@pytest.mark.asyncio
async def test_create_and_query_entities(db_session):
    # 1. Organization
    org = Organization(name="Acme Autonomous Corp", slug="acme-corp")
    db_session.add(org)
    await db_session.flush()
    assert org.id is not None

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
    await db_session.flush()

    # 4. Policy & PolicyVersion & Assignment
    policy = Policy(
        organization_id=org.id,
        name="Standard Cloud Procurement Policy",
        description="Policies for cloud infrastructure spend",
        is_active=True,
        current_version=1,
    )
    db_session.add(policy)
    await db_session.flush()

    p_version = PolicyVersion(
        policy_id=policy.id,
        version=1,
        max_amount_per_transaction=decimal.Decimal("500.00"),
        max_amount_per_day=decimal.Decimal("2000.00"),
        approval_threshold_amount=decimal.Decimal("250.00"),
        allowed_suppliers=["mock_supplier_a", "mock_supplier_b"],
        allowed_currencies=["USD"],
    )
    db_session.add(p_version)

    assignment = AgentPolicyAssignment(
        agent_id=agent.id,
        policy_id=policy.id,
        is_active=True,
    )
    db_session.add(assignment)
    await db_session.flush()

    # 5. Budget & Reservation
    budget = Budget(
        organization_id=org.id,
        agent_id=agent.id,
        name="Q4 Compute Budget",
        currency="USD",
        allocated_amount=decimal.Decimal("5000.00"),
        reserved_amount=decimal.Decimal("0.00"),
        spent_amount=decimal.Decimal("0.00"),
        start_date=datetime.datetime.now(datetime.timezone.utc),
        is_active=True,
    )
    db_session.add(budget)
    await db_session.flush()

    # 6. Supplier
    supplier = Supplier(
        code="mock_supplier_a",
        name="Mock Cloud Provider A",
        is_active=True,
        reliability_score=decimal.Decimal("0.98"),
    )
    db_session.add(supplier)
    await db_session.flush()

    # 7. Purchase Request
    pr = PurchaseRequest(
        organization_id=org.id,
        agent_id=agent.id,
        item_description="2x Standard Cloud Compute Instances",
        category="compute",
        max_budget=decimal.Decimal("300.00"),
        currency="USD",
        requirements={"vcpus": 4, "ram_gb": 16},
        status=PurchaseStatus.REQUESTED,
    )
    db_session.add(pr)
    await db_session.flush()

    # 8. Supplier Quote
    quote = SupplierQuote(
        purchase_request_id=pr.id,
        supplier_id=supplier.id,
        supplier_name=supplier.name,
        item_id="instance-c4-large",
        unit_price=decimal.Decimal("120.00"),
        quantity=2,
        total_amount=decimal.Decimal("240.00"),
        currency="USD",
        estimated_delivery_days=0,
        raw_quote_data={"sku": "compute-4"},
    )
    db_session.add(quote)
    await db_session.flush()

    # 9. Recommendation
    rec = Recommendation(
        purchase_request_id=pr.id,
        provider_type="mock",
        recommended_quote_id=quote.id,
        reasoning="Lowest total price meeting all hardware requirements.",
        comparison_scores={"price_score": 1.0, "reliability_score": 0.98},
        is_accepted=True,
    )
    db_session.add(rec)
    await db_session.flush()

    # 10. Budget Reservation
    reservation = BudgetReservation(
        budget_id=budget.id,
        purchase_request_id=pr.id,
        amount=decimal.Decimal("240.00"),
        currency="USD",
        status=ReservationStatus.ACTIVE,
    )
    db_session.add(reservation)
    await db_session.flush()

    # 11. Approval
    approval = Approval(
        purchase_request_id=pr.id,
        approver_id=user.id,
        status=ApprovalStatus.PENDING,
        notes="Awaiting manager sign-off",
    )
    db_session.add(approval)
    await db_session.flush()

    # 12. Payment Attempt
    payment = PaymentAttempt(
        purchase_request_id=pr.id,
        provider="paypal",
        status=PaymentStatus.ORDER_CREATED,
        amount=decimal.Decimal("240.00"),
        currency="USD",
        provider_order_id="PAYPAL-ORDER-123",
        idempotency_key="idemp-key-test-1",
        approval_url="https://sandbox.paypal.com/checkout?token=123",
    )
    db_session.add(payment)
    await db_session.flush()

    # 13. Transaction
    tx = Transaction(
        organization_id=org.id,
        purchase_request_id=pr.id,
        budget_id=budget.id,
        type=TransactionType.PURCHASE,
        status=TransactionStatus.PENDING,
        amount=decimal.Decimal("240.00"),
        currency="USD",
        provider_transaction_id="PAYPAL-CAPTURE-123",
    )
    db_session.add(tx)
    await db_session.flush()

    # 14. Webhook Event
    wh = WebhookEvent(
        provider="paypal",
        provider_event_id="WH-123456789",
        event_type="PAYMENT.CAPTURE.COMPLETED",
        payload={"id": "WH-123456789", "event_type": "PAYMENT.CAPTURE.COMPLETED"},
        is_processed=False,
    )
    db_session.add(wh)
    await db_session.flush()

    # 15. Audit Event
    audit = AuditEvent(
        organization_id=org.id,
        actor_type="AGENT",
        actor_id=str(agent.id),
        action="PURCHASE_REQUESTED",
        entity_type="purchase_request",
        entity_id=str(pr.id),
        metadata_json={"amount": "240.00", "currency": "USD"},
    )
    db_session.add(audit)
    await db_session.commit()

    # Verification queries
    stmt = select(PurchaseRequest).where(PurchaseRequest.id == pr.id)
    result = await db_session.scalar(stmt)
    assert result is not None
    assert result.max_budget == decimal.Decimal("300.00")
    assert result.status == PurchaseStatus.REQUESTED
