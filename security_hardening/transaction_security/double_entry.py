"""Double-Entry Ledger Integrity and Balance Invariant Verifiers."""

import decimal
from typing import Optional
from app.models.budget import Budget
from security_hardening.core.errors import SecurityHardeningError


class LedgerInvariantViolationError(SecurityHardeningError):
    def __init__(self, message: str, details: dict):
        super().__init__(
            message=message,
            code="LEDGER_INVARIANT_VIOLATION",
            details=details,
            status_code=500,
        )


class DoubleEntryVerifier:
    """Verifies that mathematical balance conservation holds across all financial mutations."""

    @staticmethod
    def verify_budget_invariants(budget: Budget) -> None:
        """Enforce:
        1. Allocated == Reserved + Spent + Available
        2. Reserved >= 0
        3. Spent >= 0
        4. Allocated >= 0
        """
        allocated = budget.allocated_amount
        reserved = budget.reserved_amount
        spent = budget.spent_amount
        available = budget.available_amount

        # Check non-negativity
        if reserved < decimal.Decimal("0.00"):
            raise LedgerInvariantViolationError(
                f"Negative reserved amount in budget {budget.id}: {reserved}",
                details={"budget_id": str(budget.id), "reserved": str(reserved)},
            )
        if spent < decimal.Decimal("0.00"):
            raise LedgerInvariantViolationError(
                f"Negative spent amount in budget {budget.id}: {spent}",
                details={"budget_id": str(budget.id), "spent": str(spent)},
            )
        if allocated < decimal.Decimal("0.00"):
            raise LedgerInvariantViolationError(
                f"Negative allocated amount in budget {budget.id}: {allocated}",
                details={"budget_id": str(budget.id), "allocated": str(allocated)},
            )

        # Balance conservation check
        expected_total = reserved + spent + available
        if allocated != expected_total:
            raise LedgerInvariantViolationError(
                f"Budget conservation violated for budget {budget.id}: "
                f"Allocated ({allocated}) != Reserved ({reserved}) + Spent ({spent}) + Available ({available})",
                details={
                    "budget_id": str(budget.id),
                    "allocated": str(allocated),
                    "expected_total": str(expected_total),
                    "variance": str(allocated - expected_total),
                },
            )

