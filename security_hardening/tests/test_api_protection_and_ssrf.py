"""Tests for API Rate Limiting, DoS Defense, SSRF Protection, and Input Validation."""

import pytest
from security_hardening.api_protection.input_validation import InputValidationGuard, InputValidationError
from security_hardening.api_protection.rate_limiter import MultiTierRateLimiter, TokenBucket
from security_hardening.api_protection.redirect_validator import OpenRedirectError, RedirectValidator
from security_hardening.api_protection.request_limits import RequestLimitGuard
from security_hardening.api_protection.ssrf_protection import SSRFBlockedError, SSRFGuard
from security_hardening.core.errors import PayloadTooLargeError, RateLimitExceededError


def test_token_bucket_exhaustion():
    bucket = TokenBucket(capacity=3.0, replenish_rate=0.0)
    assert bucket.consume(1.0) is True
    assert bucket.consume(1.0) is True
    assert bucket.consume(1.0) is True
    # Exhausted
    assert bucket.consume(1.0) is False


def test_rate_limiter_ip_and_auth_lockout():
    limiter = MultiTierRateLimiter()

    # Lockout test
    identifier = "admin@victim.com"
    for _ in range(4):
        limiter.record_auth_failure(identifier)
    # 4th failure does not lock yet
    limiter.check_auth_lockout(identifier)

    # 5th failure triggers lockout
    limiter.record_auth_failure(identifier)
    with pytest.raises(RateLimitExceededError, match="Account temporarily locked"):
        limiter.check_auth_lockout(identifier)

    # Success clears lockout
    limiter.record_auth_success(identifier)
    limiter.check_auth_lockout(identifier)  # Should not raise


def test_payload_size_enforcement():
    # Below limit (OK)
    RequestLimitGuard.enforce_body_size(b"x" * 1024, max_bytes=2048)

    # Exceeds limit (Raises 413)
    with pytest.raises(PayloadTooLargeError):
        RequestLimitGuard.enforce_body_size(b"x" * 4096, max_bytes=2048)


def test_input_validation_content_type_and_mass_assignment():
    # Content-type check
    InputValidationGuard.validate_content_type("application/json; charset=utf-8")
    with pytest.raises(InputValidationError, match="Unsupported media type"):
        InputValidationGuard.validate_content_type("text/plain")

    # Mass assignment key stripping
    untrusted_payload = {
        "item_description": "Server rack",
        "quantity": 2,
        "is_admin": True,
        "role": "ADMIN",
        "allocated_amount": "999999.00",
    }
    clean = InputValidationGuard.sanitize_untrusted_payload(untrusted_payload)
    assert clean["item_description"] == "Server rack"
    assert clean["quantity"] == 2
    assert "is_admin" not in clean
    assert "role" not in clean
    assert "allocated_amount" not in clean


def test_ssrf_protection_blocks_internal_and_metadata_ips():
    # Forbidden targets
    with pytest.raises(SSRFBlockedError):
        SSRFGuard.validate_outbound_url("http://127.0.0.1:8000/internal")

    with pytest.raises(SSRFBlockedError):
        SSRFGuard.validate_outbound_url("http://localhost/admin")

    with pytest.raises(SSRFBlockedError):
        SSRFGuard.validate_outbound_url("http://169.254.169.254/latest/meta-data")

    with pytest.raises(SSRFBlockedError):
        SSRFGuard.validate_outbound_url("http://10.0.0.5:5432/secret")

    with pytest.raises(SSRFBlockedError):
        SSRFGuard.validate_outbound_url("file:///etc/passwd")


def test_redirect_validator():
    # Permitted redirects
    RedirectValidator.validate_redirect_url("https://aeon-control.vercel.app/payments/success")
    RedirectValidator.validate_redirect_url("/dashboard")

    # Open redirect attack target
    with pytest.raises(OpenRedirectError):
        RedirectValidator.validate_redirect_url("https://evil-phishing-site.com/steal-creds")

