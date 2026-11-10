import decimal
import datetime
import uuid
from app.core.constants import PolicyReasonCode
from app.engines.policy_engine import DeterministicPolicyEngine
from app.models.agent import Agent
from app.models.budget import Budget
from app.models.policy import Policy, PolicyVersion


def test_deterministic_policy_all_hard_violations_and_approval():
    org_id = uuid.uuid4()
    agent = Agent(id=uuid.uuid4(), organization_id=org_id, name="TestBot", is_active=True)
    policy = Policy(id=uuid.uuid4(), organization_id=org_id, name="Infra Policy", is_active=True, current_version=1)
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

    # 1. Clean pass without approval required ($150 <= $200)
    d1 = DeterministicPolicyEngine.evaluate(
        agent=agent,
        policy=policy,
        policy_version=version,
        budget=budget,
        supplier_code="mock_supplier_a",
        amount=decimal.Decimal("150.00"),
        currency="USD",
    )
    assert d1.allowed is True
    assert d1.requires_approval is False
    assert PolicyReasonCode.POLICY_PASSED.value in d1.reason_codes
    assert d1.approved_max_amount == decimal.Decimal("150.00")

    # 2. Clean pass with human approval required ($350 > $200)
    d2 = DeterministicPolicyEngine.evaluate(
        agent=agent,
        policy=policy,
        policy_version=version,
        budget=budget,
        supplier_code="mock_supplier_a",
        amount=decimal.Decimal("350.00"),
        currency="USD",
    )
    assert d2.allowed is True
    assert d2.requires_approval is True
    assert PolicyReasonCode.APPROVAL_REQUIRED_AMOUNT_THRESHOLD.value in d2.reason_codes

    # 3. Hard violation: Agent inactive
    inactive_agent = Agent(id=uuid.uuid4(), organization_id=org_id, name="InactiveBot", is_active=False)
    d3 = DeterministicPolicyEngine.evaluate(
        agent=inactive_agent,
        policy=policy,
        policy_version=version,
        budget=budget,
        supplier_code="mock_supplier_a",
        amount=decimal.Decimal("100.00"),
        currency="USD",
    )
    assert d3.allowed is False
    assert PolicyReasonCode.AGENT_INACTIVE.value in d3.reason_codes

    # 4. Hard violation: No active policy assigned
    d4 = DeterministicPolicyEngine.evaluate(
        agent=agent,
        policy=None,
        policy_version=None,
        budget=budget,
        supplier_code="mock_supplier_a",
        amount=decimal.Decimal("100.00"),
        currency="USD",
    )
    assert d4.allowed is False
    assert PolicyReasonCode.NO_ACTIVE_POLICY.value in d4.reason_codes

    # 5. Hard violation: Unsupported currency (EUR instead of USD)
    d5 = DeterministicPolicyEngine.evaluate(
        agent=agent,
        policy=policy,
        policy_version=version,
        budget=budget,
        supplier_code="mock_supplier_a",
        amount=decimal.Decimal("100.00"),
        currency="EUR",
    )
    assert d5.allowed is False
    assert PolicyReasonCode.UNSUPPORTED_CURRENCY.value in d5.reason_codes

    # 6. Hard violation: Supplier not in allow-list
    d6 = DeterministicPolicyEngine.evaluate(
        agent=agent,
        policy=policy,
        policy_version=version,
        budget=budget,
        supplier_code="rogue_supplier",
        amount=decimal.Decimal("100.00"),
        currency="USD",
    )
    assert d6.allowed is False
    assert PolicyReasonCode.SUPPLIER_NOT_ALLOWED.value in d6.reason_codes

    # 7. Hard violation: Per-transaction spending limit exceeded ($550 > $500)
    d7 = DeterministicPolicyEngine.evaluate(
        agent=agent,
        policy=policy,
        policy_version=version,
        budget=budget,
        supplier_code="mock_supplier_a",
        amount=decimal.Decimal("550.00"),
        currency="USD",
    )
    assert d7.allowed is False
    assert PolicyReasonCode.PER_TRANSACTION_LIMIT_EXCEEDED.value in d7.reason_codes

    # 8. Hard violation: Daily limit exceeded ($1300 already + $300 = $1600 > $1500)
    d8 = DeterministicPolicyEngine.evaluate(
        agent=agent,
        policy=policy,
        policy_version=version,
        budget=budget,
        supplier_code="mock_supplier_a",
        amount=decimal.Decimal("300.00"),
        currency="USD",
        daily_spent_and_reserved=decimal.Decimal("1300.00"),
    )
    assert d8.allowed is False
    assert PolicyReasonCode.DAILY_LIMIT_EXCEEDED.value in d8.reason_codes

    # 9. Hard violation: Insufficient available budget ($1800 spent + $300 requested > $2000 allocated)
    exhausted_budget = Budget(
        id=uuid.uuid4(),
        organization_id=org_id,
        name="Exhausted Budget",
        currency="USD",
        allocated_amount=decimal.Decimal("2000.00"),
        reserved_amount=decimal.Decimal("100.00"),
        spent_amount=decimal.Decimal("1800.00"),  # available = 100
        start_date=datetime.datetime.now(datetime.timezone.utc),
        is_active=True,
    )
    d9 = DeterministicPolicyEngine.evaluate(
        agent=agent,
        policy=policy,
        policy_version=version,
        budget=exhausted_budget,
        supplier_code="mock_supplier_a",
        amount=decimal.Decimal("150.00"),  # 150 > 100 available
        currency="USD",
    )
    assert d9.allowed is False
    assert PolicyReasonCode.INSUFFICIENT_BUDGET.value in d9.reason_codes
