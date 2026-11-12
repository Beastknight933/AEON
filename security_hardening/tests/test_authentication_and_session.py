"""Tests for Advanced Authentication, MFA, Refresh Tokens, and Session Security."""

import time
import pytest
from security_hardening.authentication.mfa import RecoveryCodeManager, TOTPEngine
from security_hardening.authentication.passkeys import PasskeyManager
from security_hardening.authentication.session import SessionRegistry
from security_hardening.authentication.step_up import StepUpAuthManager
from security_hardening.authentication.tokens import TokenSecurityManager
from security_hardening.core.errors import StepUpAuthenticationRequiredError


def test_totp_mfa_generation_and_verification():
    totp = TOTPEngine(step_seconds=30, digits=6)
    secret = totp.generate_secret()
    assert len(secret) >= 16

    now = time.time()
    code = totp.generate_code(secret, timestamp=now)
    assert len(code) == 6
    assert code.isdigit()

    # Valid verification
    assert totp.verify_code(secret, code, timestamp=now) is True

    # Invalid code
    assert totp.verify_code(secret, "000000", timestamp=now) is False

    # Clock drift tolerance (+30s)
    drift_code = totp.generate_code(secret, timestamp=now + 30)
    assert totp.verify_code(secret, drift_code, timestamp=now, drift_steps=1) is True


def test_mfa_recovery_codes_single_use():
    plaintexts, hashes = RecoveryCodeManager.generate_recovery_codes(5)
    assert len(plaintexts) == 5
    assert len(hashes) == 5

    test_code = plaintexts[0]
    # 1. First consumption succeeds
    valid, remaining = RecoveryCodeManager.verify_and_consume(test_code, hashes)
    assert valid is True
    assert len(remaining) == 4

    # 2. Second consumption fails (prevent replay)
    valid_second, _ = RecoveryCodeManager.verify_and_consume(test_code, remaining)
    assert valid_second is False


def test_refresh_token_rotation_and_theft_detection():
    mgr = TokenSecurityManager()
    user_id = "user-123"
    org_id = "org-456"

    # 1. Issue initial token
    token_1, fam_id = mgr.issue_refresh_token(user_id, org_id)

    # 2. Normal rotation: token_1 -> token_2
    token_2, u, o = mgr.rotate_refresh_token(token_1, fam_id)
    assert token_2 != token_1
    assert u == user_id

    # 3. Normal rotation: token_2 -> token_3
    token_3, _, _ = mgr.rotate_refresh_token(token_2, fam_id)
    assert token_3 != token_2

    # 4. Token Theft Attack: Attacker presents already-retired token_1
    with pytest.raises(ValueError, match="reuse detected"):
        mgr.rotate_refresh_token(token_1, fam_id)

    # 5. Verify the entire token family is now permanently revoked!
    with pytest.raises(ValueError, match="revoked"):
        mgr.rotate_refresh_token(token_3, fam_id)


def test_session_monitoring_and_revocation():
    registry = SessionRegistry()
    s = registry.create_session("u1", "org1", "192.168.1.10", "Mozilla/5.0")
    assert s.is_active is True

    # Lookup
    found = registry.get_session(s.session_id)
    assert found is not None
    assert found.session_id == s.session_id

    # Revocation
    registry.revoke_session(s.session_id)
    assert registry.get_session(s.session_id) is None


def test_step_up_authentication():
    manager = StepUpAuthManager()
    token = manager.create_step_up_token(user_id="u1", operation="policy:change")
    assert token.startswith("stepup_")

    # Valid verification and consumption
    assert manager.verify_and_consume_token(token, "u1", "policy:change") is True

    # Replay attack (consumed token reused)
    with pytest.raises(StepUpAuthenticationRequiredError, match="already been consumed"):
        manager.verify_and_consume_token(token, "u1", "policy:change")


def test_passkey_options_generation():
    pm = PasskeyManager()
    opts = pm.generate_registration_options("user-42", "cfo@aeon.local")
    assert "challenge" in opts
    assert opts["rp"]["name"] == "AEON Procurement"
    assert len(opts["pubKeyCredParams"]) >= 2

