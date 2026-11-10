from typing import Any, Dict, Optional


class AeonBaseException(Exception):
    def __init__(
        self,
        message: str,
        code: str = "INTERNAL_SERVER_ERROR",
        status_code: int = 500,
        details: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or {}


class AuthenticationError(AeonBaseException):
    def __init__(self, message: str = "Authentication failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="AUTHENTICATION_FAILED",
            status_code=401,
            details=details,
        )


class InvalidCredentialsError(AeonBaseException):
    def __init__(self, message: str = "Invalid credentials provided", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="INVALID_CREDENTIALS",
            status_code=401,
            details=details,
        )


class AuthorizationError(AeonBaseException):
    def __init__(self, message: str = "Permission denied", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="PERMISSION_DENIED",
            status_code=403,
            details=details,
        )


class NotFoundError(AeonBaseException):
    def __init__(self, resource: str, identifier: Any):
        super().__init__(
            message=f"{resource} with identifier '{identifier}' not found",
            code="RESOURCE_NOT_FOUND",
            status_code=404,
            details={"resource": resource, "identifier": str(identifier)},
        )


class ConflictError(AeonBaseException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="RESOURCE_CONFLICT",
            status_code=409,
            details=details,
        )


class PolicyViolationError(AeonBaseException):
    def __init__(self, message: str, reason_codes: Optional[list] = None, details: Optional[Dict[str, Any]] = None):
        merged_details = details or {}
        if reason_codes:
            merged_details["reason_codes"] = reason_codes
        super().__init__(
            message=message,
            code="POLICY_VIOLATION",
            status_code=422,
            details=merged_details,
        )


class BudgetExceededError(AeonBaseException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="BUDGET_EXCEEDED",
            status_code=422,
            details=details,
        )


class StateTransitionError(AeonBaseException):
    def __init__(self, current_state: str, attempted_state: str, entity: str = "Entity"):
        super().__init__(
            message=f"Invalid {entity} state transition from '{current_state}' to '{attempted_state}'",
            code="INVALID_STATE_TRANSITION",
            status_code=400,
            details={
                "entity": entity,
                "current_state": current_state,
                "attempted_state": attempted_state,
            },
        )


class PaymentError(AeonBaseException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="PAYMENT_ERROR",
            status_code=400,
            details=details,
        )


class WebhookVerificationError(AeonBaseException):
    def __init__(self, message: str = "PayPal webhook verification failed", details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="WEBHOOK_VERIFICATION_FAILED",
            status_code=400,
            details=details,
        )


class MLRecommendationError(AeonBaseException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="ML_RECOMMENDATION_ERROR",
            status_code=502,
            details=details,
        )


class SupplierError(AeonBaseException):
    def __init__(self, message: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(
            message=message,
            code="SUPPLIER_ERROR",
            status_code=502,
            details=details,
        )
