"""Safe security exception classes with standardized error reporting."""

from typing import Any, Dict, Optional


class SecurityHardeningError(Exception):
    """Base exception for all security hardening violations."""

    def __init__(
        self,
        message: str,
        code: str = "SECURITY_VIOLATION",
        details: Optional[Dict[str, Any]] = None,
        status_code: int = 400,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.status_code = status_code

    def to_envelope(self) -> Dict[str, Any]:
        """Format as consistent AEON error envelope."""
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "details": self.details,
            }
        }


class RateLimitExceededError(SecurityHardeningError):
    def __init__(self, message: str = "Rate limit exceeded. Try again later.", retry_after: int = 60):
        super().__init__(
            message=message,
            code="RATE_LIMIT_EXCEEDED",
            details={"retry_after_seconds": retry_after},
            status_code=429,
        )


class PayloadTooLargeError(SecurityHardeningError):
    def __init__(self, max_bytes: int, received_bytes: int):
        super().__init__(
            message=f"Request payload exceeds maximum allowed size ({max_bytes} bytes).",
            code="PAYLOAD_TOO_LARGE",
            details={"max_bytes": max_bytes, "received_bytes": received_bytes},
            status_code=413,
        )


class AgentKillSwitchError(SecurityHardeningError):
    def __init__(self, agent_id: str, reason: str = "Agent execution halted by emergency kill switch"):
        super().__init__(
            message=reason,
            code="AGENT_KILL_SWITCH_ACTIVE",
            details={"agent_id": agent_id},
            status_code=403,
        )


class StepUpAuthenticationRequiredError(SecurityHardeningError):
    def __init__(self, operation: str, message: str = "Step-up authentication required for this sensitive operation"):
        super().__init__(
            message=message,
            code="STEP_UP_AUTH_REQUIRED",
            details={"operation": operation},
            status_code=403,
        )


class PromptInjectionDetectedError(SecurityHardeningError):
    def __init__(self, pattern: str):
        super().__init__(
            message="Suspicious prompt injection pattern detected in input text.",
            code="PROMPT_INJECTION_DETECTED",
            details={"threat_pattern": pattern},
            status_code=400,
        )


class SSRFBlockedError(SecurityHardeningError):
    def __init__(self, destination: str):
        super().__init__(
            message="Outbound network access to internal/private target is forbidden.",
            code="SSRF_DESTINATION_FORBIDDEN",
            details={"destination": destination},
            status_code=403,
        )


class CryptographicOperationError(SecurityHardeningError):
    def __init__(self, message: str = "Cryptographic verification or decryption failed"):
        super().__init__(
            message=message,
            code="CRYPTOGRAPHIC_ERROR",
            status_code=500,
        )

