"""Tests for Financial State Invariants, Double-Entry Verification, Audit Hash Chains, and Redaction."""

import datetime
import decimal
import uuid
import pytest
from app.core.constants import PaymentStatus, ReservationStatus
from app.core.errors import WebhookVerificationError
from app.models.budget import Budget
from security_hardening.audit.tamper_evident import TamperEvidentAuditLedger
from security_hardening.core.errors import SecurityHardeningError
from security_hardening.integrations.webhook_guard import EnterpriseWebhookGuard
from security_hardening.monitoring.redactor import SensitiveDataRedactor
from security_hardening.transaction_security.double_entry import DoubleEntryVerifier, LedgerInvariantViolationError
from security_hardening.transaction_security.duplicate_detector import DuplicateTransactionDetector, DuplicateTransactionError
from security_hardening.transaction_security.state_validator import FinancialStateValidator, InvalidFinancialTransitionError


def test_financial_state_machine_validations():
    # Legal transitions
    FinancialStateValidator.validate_payment_transition(PaymentStatus.ORDER_CREATED, PaymentStatus.BUYER_APPROVAL_PENDING)
    FinancialStateValidator.validate_payment_transition(PaymentStatus.CAPTURE_PENDING, PaymentStatus.COMPLETED)

    # Illegal transition: cannot jump from COMPLETED back to ORDER_CREATED or NOT_STARTED
    with pytest.raises(InvalidFinancialTransitionError):
        FinancialStateValidator.validate_payment_transition(PaymentStatus.COMPLETED, PaymentStatus.ORDER_CREATED)

    with pytest.raises(InvalidFinancialTransitionError):
        FinancialStateValidator.validate_reservation_transition(ReservationStatus.SETTLED, ReservationStatus.ACTIVE)


def test_duplicate_transaction_detector():
    detector = DuplicateTransactionDetector(window_seconds=10)
    agent = "agent-x"

    # First submission OK
    fp1 = detector.check_and_record(agent, "Server 1U", "compute", "150.00", "USD")
    assert fp1 is not None

    # Immediate identical duplicate within window -> DuplicateTransactionError
    with pytest.raises(DuplicateTransactionError):
        detector.check_and_record(agent, "Server 1U", "compute", "150.00", "USD")

    # Different item -> OK
    fp2 = detector.check_and_record(agent, "Storage Disk", "storage", "150.00", "USD")
    assert fp2 != fp1


def test_double_entry_budget_conservation():
    budget = Budget(
        id=uuid.uuid4(),
        organization_id=uuid.uuid4(),
        name="Q1 Engineering Budget",
        currency="USD",
        allocated_amount=decimal.Decimal("1000.00"),
        reserved_amount=decimal.Decimal("300.00"),
        spent_amount=decimal.Decimal("200.00"),
        # available = 1000 - 300 - 200 = 500
        start_date=datetime.datetime.now(datetime.timezone.utc),
        is_active=True,
    )

    # Invariant holds
    DoubleEntryVerifier.verify_budget_invariants(budget)

    # Corrupt reserved amount (negative)
    budget.reserved_amount = decimal.Decimal("-50.00")
    with pytest.raises(LedgerInvariantViolationError, match="Negative reserved amount"):
        DoubleEntryVerifier.verify_budget_invariants(budget)


def test_tamper_evident_audit_hash_chain_detection():
    ledger = TamperEvidentAuditLedger()

    # Append blocks
    b1 = ledger.append_event("LOGIN", "u1", "org1", {"ip": "1.1.1.1"}, "2026-11-12T00:00:00Z")
    b2 = ledger.append_event("PURCHASE", "agent1", "pr1", {"amt": "100"}, "2026-11-12T00:01:00Z")
    b3 = ledger.append_event("CAPTURE", "paypal", "tx1", {"amt": "100"}, "2026-11-12T00:02:00Z")

    # 1. Verification succeeds on untampered chain
    valid, err, seq = ledger.verify_integrity()
    assert valid is True
    assert err is None

    # 2. Tampering attack: Adversary maliciously modifies block 2 payload in database
    b2.payload["amt"] = "99999"

    # 3. Verification detects tampering and identifies corrupted block sequence
    valid_tampered, err_tampered, seq_tampered = ledger.verify_integrity()
    assert valid_tampered is False
    assert "Tampered block data" in err_tampered
    assert seq_tampered == 2


def test_sensitive_data_redaction():
    log_text = "User admin logged in with password SecretPass! and bearer token Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0In0.test with agent key aeon_live_supersecretrandomtoken12345"
    clean = SensitiveDataRedactor.redact_string(log_text)

    assert "SecretPass!" not in clean
    assert "aeon_live_" not in clean
    assert "eyJhbGciOi" not in clean
    assert "[REDACTED_SECRET]" in clean

    # Dictionary redaction
    payload = {
        "user_email": "admin@aeon.local",
        "password": "CleartextPassword123!",
        "api_key": "aeon_live_key1234567890123456",
        "nested": {"client_secret": "xyz_secret", "amount": "100.00"},
    }
    cleaned_dict = SensitiveDataRedactor.redact_data(payload)
    assert cleaned_dict["user_email"] == "admin@aeon.local"
    assert cleaned_dict["password"] == "[REDACTED]"
    assert cleaned_dict["nested"]["client_secret"] == "[REDACTED]"
    assert cleaned_dict["nested"]["amount"] == "100.00"


def test_webhook_guard_security():
    guard = EnterpriseWebhookGuard()

    # 1. In non-production/testing mode, mock webhook passes
    guard.validate_incoming_webhook(
        headers={"x-mock-webhook": "true"},
        event_body={"id": "WH-1", "event_type": "PAYMENT.CAPTURE.COMPLETED"},
    )

    # 2. Non-allowlisted event types are placed in dead-letter queue
    guard.validate_incoming_webhook(
        headers={"x-mock-webhook": "true"},
        event_body={"id": "WH-UNKNOWN", "event_type": "UNSUPPORTED.BILLING.EVENT"},
    )
    dead_letters = guard.list_dead_letter_events()
    assert any(d["event_id"] == "WH-UNKNOWN" for d in dead_letters)

