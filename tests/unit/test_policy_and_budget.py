import decimal
import datetime
import uuid
import pytest
from app.core.constants import PolicyReasonCode, ReservationStatus
from app.core.errors import BudgetExceededError
from app.engines.policy_engine import DeterministicPolicyEngine
from app.models.agent import Agent
from app.models.budget import Budget
from app.models.policy import Policy, PolicyVersion
from app.models.supplier import SupplierQuote
from app.repositories.budget_repo import BudgetRepository


def test_deterministic_policy_engine_scenarios():
    org_id = uuid.uuid4()
    agent = Agent(id=uuid.uuid4(), organization_id=org_id, name="TestBot", is_active=True)
    policy = Policy(id=uuid.uuid4(), organization_id=org_id, name="Standard Policy", is_active=True, current_version=1)
    version = PolicyVersion(
        id=uuid.uuid4(),
        policy_id=policy.id,
        version=1,
        max_amount_per_transaction=decimal.Decimal("500.00"),
        max_amount_per_day=decimal.Decimal("1500.00"),
        approval_threshold_amount=decimal.Decimal("200.00"),
        allowed_suppliers=["mock_supplier_a", "mock_supplier_b"],
        allowed_currencies=["USD"],
    )
    budget = Budget(
        id=uuid.uuid4(),
        organization_id=org_id,
        name="Compute Budget",
        currency="USD",
        allocated_amount=decimal.Decimal("2000.00"),
        reserved_amount=decimal.Decimal("0.00"),
        spent_amount=decimal.Decimal("0.00"),
        start_date=datetime.datetime.now(datetime.timezone.utc),
        is_active=True,
    )

    # Scenario 1: Clean pass under approval threshold ($150)
    quote1 = SupplierQuote(
        id=uuid.uuid4(),
        purchase_request_id=uuid.uuid4(),
        supplier_id=uuid.uuid4(),
        supplier_name="Mock Provider A",
        item_id="item-1",
        unit_price=decimal.Decimal("150.00"),
        quantity=1,
        total_amount=decimal.Decimal("150.00"),
        currency="USD",
    )
    d1 = DeterministicPolicyEngine.evaluate(agent, policy, version, budget, quote1, "mock_supplier_a")
    assert d1.allowed is True
    assert d1.requires_approval is False
    assert PolicyReasonCode.POLICY_PASSED.value in d1.reason_codes

    # Scenario 2: Clean pass requiring human approval ($350 > $200 threshold)
    quote2 = SupplierQuote(
        id=uuid.uuid4(),
        purchase_request_id=uuid.uuid4(),
        supplier_id=uuid.uuid4(),
        supplier_name="Mock Provider A",
        item_id="item-2",
        unit_price=decimal.Decimal("350.00"),
        quantity=1,
        total_amount=decimal.Decimal("350.00"),
        currency="USD",
    )
    d2 = DeterministicPolicyEngine.evaluate(agent, policy, version, budget, quote2, "mock_supplier_a")
    assert d2.allowed is True
    assert d2.requires_approval is True
    assert PolicyReasonCode.APPROVAL_REQUIRED_AMOUNT_THRESHOLD.value in d2.reason_codes

    # Scenario 3: Hard block on unapproved supplier
    d3 = DeterministicPolicyEngine.evaluate(agent, policy, version, budget, quote1, "unauthorized_supplier")
    assert d3.allowed is False
    assert PolicyReasonCode.SUPPLIER_NOT_ALLOWED.value in d3.reason_codes

    # Scenario 4: Hard block exceeding per-transaction limit ($600 > $500)
    quote4 = SupplierQuote(
        id=uuid.uuid4(),
        purchase_request_id=uuid.uuid4(),
        supplier_id=uuid.uuid4(),
        supplier_name="Mock Provider A",
        item_id="item-4",
        unit_price=decimal.Decimal("600.00"),
        quantity=1,
        total_amount=decimal.Decimal("600.00"),
        currency="USD",
    )
    d4 = DeterministicPolicyEngine.evaluate(agent, policy, version, budget, quote4, "mock_supplier_a")
    assert d4.allowed is False
    assert PolicyReasonCode.PER_TRANSACTION_LIMIT_EXCEEDED.value in d4.reason_codes

    # Scenario 5: Hard block exceeding daily limit ($1200 already spent + $350 = $1550 > $1500)
    d5 = DeterministicPolicyEngine.evaluate(
        agent, policy, version, budget, quote2, "mock_supplier_a", daily_spent_and_reserved=decimal.Decimal("1200.00")
    )
    assert d5.allowed is False
    assert PolicyReasonCode.DAILY_LIMIT_EXCEEDED.value in d5.reason_codes

    # Scenario 6: Inactive agent is immediately blocked
    inactive_agent = Agent(id=uuid.uuid4(), organization_id=org_id, name="DeadBot", is_active=False)
    d6 = DeterministicPolicyEngine.evaluate(inactive_agent, policy, version, budget, quote1, "mock_supplier_a")
    assert d6.allowed is False
    assert PolicyReasonCode.AGENT_INACTIVE.value in d6.reason_codes


@pytest.mark.asyncio
async def test_budget_reservation_lifecycle(db_session):
    repo = BudgetRepository(db_session)
    org_id = uuid.uuid4()
    budget = Budget(
        organization_id=org_id,
        name="Engineering Cloud Budget",
        currency="USD",
        allocated_amount=decimal.Decimal("1000.00"),
        reserved_amount=decimal.Decimal("0.00"),
        spent_amount=decimal.Decimal("0.00"),
        start_date=datetime.datetime.now(datetime.timezone.utc),
        is_active=True,
    )
    await repo.create(budget)
    await db_session.flush()

    pr_id = uuid.uuid4()
    # 1. Reserve $400
    res = await repo.reserve_funds_atomic(budget.id, pr_id, decimal.Decimal("400.00"), "USD")
    assert res.status == ReservationStatus.ACTIVE
    assert budget.reserved_amount == decimal.Decimal("400.00")
    assert budget.available_amount == decimal.Decimal("600.00")

    # 2. Exceeding remaining budget ($700 > $600) must raise BudgetExceededError
    with pytest.raises(BudgetExceededError):
        await repo.reserve_funds_atomic(budget.id, uuid.uuid4(), decimal.Decimal("700.00"), "USD")

    # 3. Settle reservation
    settled = await repo.settle_reservation_atomic(res.id)
    assert settled.status == ReservationStatus.SETTLED
    assert budget.reserved_amount == decimal.Decimal("0.00")
    assert budget.spent_amount == decimal.Decimal("400.00")
    assert budget.available_amount == decimal.Decimal("600.00")

    # 4. Reserve another $200 and then release it
    res2 = await repo.reserve_funds_atomic(budget.id, uuid.uuid4(), decimal.Decimal("200.00"), "USD")
    assert budget.reserved_amount == decimal.Decimal("200.00")
    assert budget.available_amount == decimal.Decimal("400.00")

    released = await repo.release_reservation_atomic(res2.id)
    assert released.status == ReservationStatus.RELEASED
    assert budget.reserved_amount == decimal.Decimal("0.00")
    assert budget.available_amount == decimal.Decimal("600.00")
