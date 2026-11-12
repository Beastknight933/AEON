"""Zero-Leak Sensitive Data Redaction Filter."""

import re
from typing import Any, Dict, List, Set


class SensitiveDataRedactor:
    """Masks secrets, passwords, bearer tokens, API keys, and financial credentials from logs."""

    SENSITIVE_KEY_NAMES: Set[str] = {
        "password",
        "hashed_password",
        "secret",
        "client_secret",
        "secret_key",
        "raw_key",
        "token",
        "access_token",
        "refresh_token",
        "key_hash",
        "authorization",
        "x-agent-api-key",
        "paypal_client_secret",
        "card_number",
        "cvv",
        "ssn",
    }

    TOKEN_REGEXES = [
        re.compile(r"aeon_live_[A-Za-z0-9_-]{20,}", re.IGNORECASE),
        re.compile(r"Bearer\s+eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+", re.IGNORECASE),
        re.compile(r"\b(?:\d[ -]*?){13,16}\b"),  # Credit card numbers
    ]

    @classmethod
    def redact_string(cls, text: str) -> str:
        """Mask secrets embedded in arbitrary string logs."""
        if not text:
            return ""

        redacted = text
        for pattern in cls.TOKEN_REGEXES:
            redacted = pattern.sub("[REDACTED_SECRET]", redacted)
        # Redact password/secret values following common labels
        redacted = re.sub(
            r"((?:password|pwd|secret|passwd)\s*[:= ]\s*)([^\s,;]+)",
            r"\1[REDACTED_SECRET]",
            redacted,
            flags=re.IGNORECASE,
        )
        return redacted

    @classmethod
    def redact_data(cls, data: Any) -> Any:
        """Recursively redact dictionaries and lists before serialization or logging."""
        if isinstance(data, dict):
            clean_dict = {}
            for k, v in data.items():
                if str(k).lower() in cls.SENSITIVE_KEY_NAMES:
                    clean_dict[k] = "[REDACTED]"
                else:
                    clean_dict[k] = cls.redact_data(v)
            return clean_dict

        if isinstance(data, list):
            return [cls.redact_data(item) for item in data]

        if isinstance(data, str):
            return cls.redact_string(data)

        return data

