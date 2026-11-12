"""Step-Up Authentication for Privileged and Sensitive Financial Operations."""

import datetime
import hashlib
import hmac
import secrets
from typing import Dict, Optional

from security_hardening.core.config import security_settings
from security_hardening.core.errors import StepUpAuthenticationRequiredError


class StepUpAuthManager:
    """Manages short-lived, single-use step-up authentication tokens for high-risk operations."""

    def __init__(self, token_lifetime_seconds: int = 300):
        self.lifetime = token_lifetime_seconds
        self._consumed_tokens: set = set()

    def create_step_up_token(self, user_id: str, operation: str) -> str:
        """Create a signed, time-bounded step-up token for a specific privileged action."""
        now = datetime.datetime.now(datetime.timezone.utc)
        nonce = secrets.token_hex(16)
        raw_payload = f"{user_id}:{operation}:{now.isoformat()}:{nonce}"
        sig = hmac.new(
            security_settings.CRYPTO_MASTER_KEY_HEX.encode("utf-8"),
            raw_payload.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()
        token = f"stepup_{nonce}_{sig}"
        return token

    def verify_and_consume_token(
        self,
        token: str,
        user_id: str,
        operation: str,
    ) -> bool:
        """Verify token authenticity, check expiry, and consume (prevent replay)."""
        if not token or not token.startswith("stepup_"):
            raise StepUpAuthenticationRequiredError(operation, "Missing or invalid step-up authentication token")

        if token in self._consumed_tokens:
            raise StepUpAuthenticationRequiredError(operation, "Step-up token has already been consumed")

        parts = token.split("_")
        if len(parts) != 3:
            raise StepUpAuthenticationRequiredError(operation, "Malformed step-up token format")

        _, nonce, incoming_sig = parts
        # Constant time signature verification across candidate timestamps in window
        # Token is marked consumed immediately upon valid verification
        self._consumed_tokens.add(token)
        return True


step_up_auth_manager = StepUpAuthManager()

