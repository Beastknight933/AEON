"""Security hardening settings and feature toggles."""

import os
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict


class SecuritySettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="SECURITY_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Master Toggle
    ENABLED: bool = True

    # Mode: "advisory" (logs/monitors only) or "enforcement" (blocks attacks)
    # Default is enforcement for clear security boundaries, with graceful fallbacks
    ENFORCEMENT_MODE: bool = True

    # API Protection Defaults
    MAX_REQUEST_BODY_BYTES: int = 1_048_576  # 1 MB max payload
    REQUEST_TIMEOUT_SECONDS: float = 30.0
    RATE_LIMIT_ENABLED: bool = True
    RATE_LIMIT_GLOBAL_RPS: int = 100
    RATE_LIMIT_PER_IP_BURST: int = 60
    RATE_LIMIT_PER_IP_REPLENISH: float = 10.0  # tokens per second
    RATE_LIMIT_AGENT_BURST: int = 120
    RATE_LIMIT_AGENT_REPLENISH: float = 20.0
    AUTH_ATTEMPTS_MAX_BURST: int = 5
    AUTH_ATTEMPTS_LOCKOUT_SECONDS: int = 300

    # Cryptography
    CRYPTO_MASTER_KEY_HEX: str = os.getenv(
        "SECURITY_MASTER_KEY",
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )
    KEY_ROTATION_GRACE_PERIOD_DAYS: int = 30

    # Authentication & Session
    MFA_ENABLED: bool = True
    MFA_ISSUER_NAME: str = "AEON Control Plane"
    STEP_UP_TIMEOUT_SECONDS: int = 300  # 5 minutes
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Agent Boundary
    AGENT_KILL_SWITCH_ENABLED: bool = True
    PROMPT_INJECTION_SCAN_ENABLED: bool = True
    AGENT_MAX_ACTIONS_PER_MINUTE: int = 60

    # Financial & Double-Entry Invariants
    LEDGER_INTEGRITY_CHECK_ENABLED: bool = True
    DUPLICATE_TX_WINDOW_SECONDS: int = 60

    # Webhook Protection
    WEBHOOK_MAX_AGE_SECONDS: int = 300  # 5 minute replay window
    ALLOWED_WEBHOOK_EVENT_TYPES: List[str] = [
        "CHECKOUT.ORDER.APPROVED",
        "PAYMENT.CAPTURE.COMPLETED",
        "PAYMENT.CAPTURE.DENIED",
        "PAYMENT.CAPTURE.REFUNDED",
        "PAYMENT.CAPTURE.REVERSED",
        "PAYMENT.CAPTURE.PENDING",
    ]

    # Audit & Monitoring
    AUDIT_HASH_CHAIN_ENABLED: bool = True
    SENSITIVE_DATA_REDACTION_ENABLED: bool = True


security_settings = SecuritySettings()

