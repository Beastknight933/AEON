"""Financial State Machine Invariant Validator."""

from typing import Dict, Set
from app.core.constants import PaymentStatus, PurchaseStatus, ReservationStatus, TransactionStatus
from security_hardening.core.errors import SecurityHardeningError


class InvalidFinancialTransitionError(SecurityHardeningError):
    def __init__(self, entity: str, current_state: str, attempted_state: str):
        super().__init__(
            message=f"Illegal financial state transition for {entity}: {current_state} -> {attempted_state}",
            code="ILLEGAL_FINANCIAL_STATE_TRANSITION",
            details={
                "entity": entity,
                "current_state": current_state,
                "attempted_state": attempted_state,
            },
            status_code=409,
        )


class FinancialStateValidator:
    """Enforces strict, irreversible financial lifecycle state transitions."""

    VALID_PAYMENT_TRANSITIONS: Dict[PaymentStatus, Set[PaymentStatus]] = {
        PaymentStatus.NOT_STARTED: {PaymentStatus.ORDER_CREATED, PaymentStatus.FAILED},
        PaymentStatus.ORDER_CREATED: {
            PaymentStatus.BUYER_APPROVAL_PENDING,
            PaymentStatus.CAPTURE_PENDING,
            PaymentStatus.FAILED,
            PaymentStatus.COMPLETED,
        },
        PaymentStatus.BUYER_APPROVAL_PENDING: {
            PaymentStatus.CAPTURE_PENDING,
            PaymentStatus.COMPLETED,
            PaymentStatus.FAILED,
        },
        PaymentStatus.CAPTURE_PENDING: {PaymentStatus.COMPLETED, PaymentStatus.FAILED},
        PaymentStatus.COMPLETED: {PaymentStatus.REFUNDED},
        PaymentStatus.FAILED: set(),
        PaymentStatus.REFUNDED: set(),
    }

    VALID_RESERVATION_TRANSITIONS: Dict[ReservationStatus, Set[ReservationStatus]] = {
        ReservationStatus.ACTIVE: {ReservationStatus.SETTLED, ReservationStatus.RELEASED},
        ReservationStatus.SETTLED: set(),
        ReservationStatus.RELEASED: set(),
    }

    @classmethod
    def validate_payment_transition(cls, current: PaymentStatus, target: PaymentStatus) -> None:
        """Verify payment transition legality."""
        if current == target:
            return  # Idempotent no-op

        allowed = cls.VALID_PAYMENT_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise InvalidFinancialTransitionError(
                entity="PaymentAttempt",
                current_state=current.value,
                attempted_state=target.value,
            )

    @classmethod
    def validate_reservation_transition(cls, current: ReservationStatus, target: ReservationStatus) -> None:
        """Verify budget reservation transition legality."""
        if current == target:
            return

        allowed = cls.VALID_RESERVATION_TRANSITIONS.get(current, set())
        if target not in allowed:
            raise InvalidFinancialTransitionError(
                entity="BudgetReservation",
                current_state=current.value,
                attempted_state=target.value,
            )

