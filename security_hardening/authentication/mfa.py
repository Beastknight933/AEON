"""RFC 6238 Time-Based One-Time Password (TOTP) and Multi-Factor Authentication.

Implemented in pure Python without mandatory external dependencies:
- RFC 6238 compliant TOTP generation and verification.
- Configurable step interval (default 30 seconds).
- Clock skew tolerance window (+/- 1 time step).
- Cryptographic backup recovery scratch codes (single-use).
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import List, Optional, Tuple


class TOTPEngine:
    """RFC 6238 Time-Based One-Time Password Engine."""

    def __init__(self, step_seconds: int = 30, digits: int = 6):
        self.step_seconds = step_seconds
        self.digits = digits

    @staticmethod
    def generate_secret(length: int = 20) -> str:
        """Generate a Base32 encoded random secret key."""
        raw_bytes = secrets.token_bytes(length)
        return base64.b32encode(raw_bytes).decode("ascii").replace("=", "")

    def generate_code(self, secret_b32: str, timestamp: Optional[float] = None) -> str:
        """Generate TOTP code for the given secret at timestamp."""
        t = int(timestamp if timestamp is not None else time.time())
        counter = t // self.step_seconds

        # Normalize base32 padding
        padded_secret = secret_b32 + "=" * ((8 - len(secret_b32) % 8) % 8)
        key = base64.b32decode(padded_secret.upper())

        counter_bytes = struct.pack(">Q", counter)
        hmac_digest = hmac.new(key, counter_bytes, hashlib.sha1).digest()

        # Dynamic truncation (RFC 4226)
        offset = hmac_digest[-1] & 0x0F
        binary = struct.unpack(">I", hmac_digest[offset : offset + 4])[0] & 0x7FFFFFFF
        code = binary % (10**self.digits)
        return str(code).zfill(self.digits)

    def verify_code(
        self,
        secret_b32: str,
        code: str,
        timestamp: Optional[float] = None,
        drift_steps: int = 1,
    ) -> bool:
        """Verify user-provided TOTP code within clock skew tolerance window."""
        clean_code = str(code).strip()
        if len(clean_code) != self.digits or not clean_code.isdigit():
            return False

        t = int(timestamp if timestamp is not None else time.time())
        current_step = t // self.step_seconds

        for offset in range(-drift_steps, drift_steps + 1):
            step_time = (current_step + offset) * self.step_seconds
            expected_code = self.generate_code(secret_b32, step_time)
            if hmac.compare_digest(clean_code, expected_code):
                return True

        return False

    def generate_provisioning_uri(self, secret_b32: str, account_name: str, issuer: str = "AEON") -> str:
        """Generate standard otpauth:// URI for Authenticator apps."""
        from urllib.parse import quote
        return f"otpauth://totp/{quote(issuer)}:{quote(account_name)}?secret={secret_b32}&issuer={quote(issuer)}&digits={self.digits}&period={self.step_seconds}"


class RecoveryCodeManager:
    """Manages single-use cryptographically hashed emergency backup recovery codes."""

    @staticmethod
    def generate_recovery_codes(count: int = 10) -> Tuple[List[str], List[str]]:
        """Generate plaintext codes for user display and SHA-256 hashes for storage.

        Returns:
            (plaintext_codes, hashed_codes)
        """
        plaintexts = [
            f"{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}-{secrets.token_hex(2).upper()}"
            for _ in range(count)
        ]
        hashes = [hashlib.sha256(c.encode("utf-8")).hexdigest() for c in plaintexts]
        return plaintexts, hashes

    @staticmethod
    def verify_and_consume(code: str, stored_hashes: List[str]) -> Tuple[bool, List[str]]:
        """Verify code against stored hashes and return updated hash list with consumed code removed."""
        normalized = code.strip().upper()
        incoming_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

        for idx, stored in enumerate(stored_hashes):
            if hmac.compare_digest(incoming_hash, stored):
                remaining = [h for i, h in enumerate(stored_hashes) if i != idx]
                return True, remaining

        return False, stored_hashes


totp_engine = TOTPEngine()

