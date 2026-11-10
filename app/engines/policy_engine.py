import decimal
import uuid
from typing import Any, List, Optional
from app.core.constants import PolicyReasonCode
from app.models.agent import Agent
from app.models.budget import Budget
from app.models.policy import Policy, PolicyVersion
from app.schemas.policy import PolicyDecision


class DeterministicPolicyEngine:
    """
    Deterministic procurement policy evaluation engine.
    Independent of ML recommendation.
    Evaluates hard policy rules and human approval thresholds.
    """

    @classmethod
    def evaluate(
        cls,
        agent: Agent,
        policy: Optional[Policy],
        policy_version: Optional[PolicyVersion],
        budget: Optional[Budget],
        supplier_code: str,
        amount: Optional[decimal.Decimal] = None,
        currency: str = "USD",
        quote: Optional[Any] = None,
        daily_spent_and_reserved: decimal.Decimal = decimal.Decimal("0.00"),
    ) -> PolicyDecision:
        if quote is not None:
            total_amount = quote.total_amount
            tx_currency = quote.currency
        elif amount is not None:
            total_amount = amount
            tx_currency = currency
        else:
            raise ValueError("Either amount or quote must be provided to evaluate policy")

        reason_codes: List[str] = []
        hard_violation = False

        # 1. Agent active status check
        if not agent.is_active:
            hard_violation = True
            reason_codes.append(PolicyReasonCode.AGENT_INACTIVE.value)

        # 2. Active policy assignment check
        if not policy or not policy.is_active or not policy_version:
            hard_violation = True
            reason_codes.append(PolicyReasonCode.NO_ACTIVE_POLICY.value)
            return PolicyDecision(
                allowed=False,
                requires_approval=False,
                reason_codes=reason_codes,
                policy_id=None,
                policy_version=None,
                approved_max_amount=None,
                currency=tx_currency,
            )

        # 3. Currency support check (Phase 1 supports USD only)
        if tx_currency != "USD" or tx_currency not in policy_version.allowed_currencies:
            hard_violation = True
            reason_codes.append(PolicyReasonCode.UNSUPPORTED_CURRENCY.value)

        # 4. Supplier allow-list check (if policy specifies a non-empty allow-list)
        if policy_version.allowed_suppliers and len(policy_version.allowed_suppliers) > 0:
            allowed_set = {s.strip().lower() for s in policy_version.allowed_suppliers}
            if supplier_code.strip().lower() not in allowed_set:
                hard_violation = True
                reason_codes.append(PolicyReasonCode.SUPPLIER_NOT_ALLOWED.value)

        # 5. Per-transaction spending limit
        if total_amount > policy_version.max_amount_per_transaction:
            hard_violation = True
            reason_codes.append(PolicyReasonCode.PER_TRANSACTION_LIMIT_EXCEEDED.value)

        # 6. Daily spending limit check
        projected_daily_total = daily_spent_and_reserved + total_amount
        if projected_daily_total > policy_version.max_amount_per_day:
            hard_violation = True
            reason_codes.append(PolicyReasonCode.DAILY_LIMIT_EXCEEDED.value)

        # 7. Available budget check
        if not budget or not budget.is_active:
            hard_violation = True
            reason_codes.append(PolicyReasonCode.INSUFFICIENT_BUDGET.value)
        else:
            available_budget = budget.allocated_amount - budget.reserved_amount - budget.spent_amount
            if available_budget < total_amount:
                hard_violation = True
                reason_codes.append(PolicyReasonCode.INSUFFICIENT_BUDGET.value)

        # If any hard constraint was violated, cannot be allowed (and human cannot override hard violation)
        if hard_violation:
            return PolicyDecision(
                allowed=False,
                requires_approval=False,
                reason_codes=reason_codes,
                policy_id=policy.id,
                policy_version=policy_version.version,
                approved_max_amount=None,
                currency=tx_currency,
            )

        # 8. Approval threshold check
        requires_approval = False
        if total_amount > policy_version.approval_threshold_amount:
            requires_approval = True
            reason_codes.append(PolicyReasonCode.APPROVAL_REQUIRED_AMOUNT_THRESHOLD.value)
        else:
            reason_codes.append(PolicyReasonCode.POLICY_PASSED.value)

        return PolicyDecision(
            allowed=True,
            requires_approval=requires_approval,
            reason_codes=reason_codes,
            policy_id=policy.id,
            policy_version=policy_version.version,
            approved_max_amount=total_amount,
            currency=tx_currency,
        )
