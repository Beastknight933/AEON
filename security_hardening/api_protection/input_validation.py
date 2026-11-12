"""Strict Input Validation, Content-Type Guards, and Mass-Assignment Protection."""

import json
from typing import Any, Dict, List, Set
from security_hardening.core.errors import SecurityHardeningError


class InputValidationError(SecurityHardeningError):
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            message=message,
            code="INPUT_VALIDATION_ERROR",
            details=details or {},
            status_code=400,
        )


class InputValidationGuard:
    FORBIDDEN_MASS_ASSIGNMENT_KEYS: Set[str] = {
        "role",
        "is_active",
        "is_admin",
        "is_superuser",
        "organization_id",
        "balance",
        "reserved_amount",
        "spent_amount",
        "allocated_amount",
        "provider_order_id",
        "provider_capture_id",
        "status",
    }

    @staticmethod
    def validate_content_type(content_type: str, allowed_types: List[str] = None) -> None:
        """Enforce permitted Content-Type header on request payloads."""
        allowed = allowed_types or ["application/json"]
        if not content_type:
            raise InputValidationError("Content-Type header is required for mutating requests.")

        main_type = content_type.split(";")[0].strip().lower()
        if main_type not in allowed:
            raise InputValidationError(
                f"Unsupported media type '{main_type}'. Expected one of: {allowed}",
                details={"received_content_type": content_type},
            )

    @classmethod
    def sanitize_untrusted_payload(
        cls,
        payload: Dict[str, Any],
        disallowed_keys: Set[str] = None,
    ) -> Dict[str, Any]:
        """Strip forbidden internal/administrative keys to prevent mass assignment."""
        keys_to_strip = disallowed_keys or cls.FORBIDDEN_MASS_ASSIGNMENT_KEYS
        stripped = {}
        for k, v in payload.items():
            if k.lower() in keys_to_strip:
                continue
            stripped[k] = v
        return stripped

    @staticmethod
    def validate_json_depth(data: Any, current_depth: int = 1, max_depth: int = 10) -> None:
        """Prevent deeply nested recursive JSON denial-of-service payloads."""
        if current_depth > max_depth:
            raise InputValidationError(f"JSON nesting depth exceeds safety threshold of {max_depth} levels.")

        if isinstance(data, dict):
            for v in data.values():
                InputValidationGuard.validate_json_depth(v, current_depth + 1, max_depth)
        elif isinstance(data, list):
            for item in data:
                InputValidationGuard.validate_json_depth(item, current_depth + 1, max_depth)

