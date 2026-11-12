"""Database Query Execution Guards, SQLi Detectors, and Column Encryption."""

import re
from typing import Any, Optional
from security_hardening.core.errors import SecurityHardeningError
from security_hardening.crypto.envelope import EnvelopeEncryptionEngine


class SQLInjectionRiskError(SecurityHardeningError):
    def __init__(self, suspicious_pattern: str):
        super().__init__(
            message="Potential SQL injection pattern detected in input parameter.",
            code="SQLI_RISK_DETECTED",
            details={"pattern": suspicious_pattern},
            status_code=400,
        )


class DatabaseSecurityGuard:
    """Detects SQL injection patterns and provides column-level encryption hooks."""

    SQLI_SUSPICIOUS_REGEXES = [
        re.compile(r"(\b(UNION(\s+ALL)?|SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE)\b.*\b(FROM|INTO|TABLE)\b)", re.IGNORECASE),
        re.compile(r"(--|#|/\*|\*/|;.*--)", re.IGNORECASE),
        re.compile(r"(\bOR\b|\bAND\b)\s+[\'\"]?\w+[\'\"]?\s*=\s*[\'\"]?\w+", re.IGNORECASE),
        re.compile(r"(\bEXEC\b|\bEXECUTE\b|\bXP_\b|\bSP_\b)", re.IGNORECASE),
    ]

    def __init__(self, encryption_engine: Optional[EnvelopeEncryptionEngine] = None):
        self.crypto = encryption_engine or EnvelopeEncryptionEngine()

    @classmethod
    def scan_for_sqli(cls, untrusted_string: str) -> None:
        """Scan free-text query parameters for classic SQL injection signatures."""
        if not untrusted_string:
            return

        for pattern in cls.SQLI_SUSPICIOUS_REGEXES:
            match = pattern.search(untrusted_string)
            if match:
                raise SQLInjectionRiskError(match.group(0))

    def encrypt_sensitive_column(self, plaintext_value: str, context_id: str) -> str:
        """Encrypt sensitive database field using envelope encryption with AAD."""
        return self.crypto.encrypt_string(plaintext_value, associated_data=context_id)

    def decrypt_sensitive_column(self, ciphertext_json: str, context_id: str) -> str:
        """Decrypt sensitive database field with AAD integrity check."""
        return self.crypto.decrypt_string(ciphertext_json, associated_data=context_id)

