"""AEON ML Module - Exception Hierarchy.

Custom exceptions for robust error handling during quote recommendation evaluation.
"""

from typing import Optional


class AEONMLError(ValueError):
    """Base exception for all AEON ML module errors.

    Inherits from ValueError to integrate seamlessly with Pydantic v2
    validation pipelines and FastAPI RequestValidationError handlers.
    """

    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class EmptyQuotesError(AEONMLError):
    """Raised when the recommendation request contains an empty list of quotes."""

    def __init__(self, message: str = "At least one supplier quote is required for recommendation.") -> None:
        super().__init__(message)


class CurrencyMismatchError(AEONMLError):
    """Raised when one or more quotes do not match the required request currency."""

    def __init__(self, request_currency: str, invalid_quotes: list) -> None:
        message = (
            f"Currency mismatch detected: Request requires '{request_currency}', "
            f"but found mismatch in quotes: {invalid_quotes}"
        )
        super().__init__(message, details={"request_currency": request_currency, "invalid_quotes": invalid_quotes})


class DuplicateQuoteIdError(AEONMLError):
    """Raised when duplicate quote IDs are detected in candidate quotes."""

    def __init__(self, duplicate_ids: list) -> None:
        message = f"Duplicate quote IDs detected in candidate quotes: {duplicate_ids}"
        super().__init__(message, details={"duplicate_ids": duplicate_ids})


class InvalidQuoteDataError(AEONMLError):
    """Raised when quote data fails business validation rules (e.g. non-positive amount)."""

    def __init__(self, message: str, details: Optional[dict] = None) -> None:
        super().__init__(message, details=details)


class ModelInferenceError(AEONMLError):
    """Raised when an internal error occurs during model scoring or reasoning generation."""

    def __init__(self, message: str, cause: Optional[Exception] = None) -> None:
        super().__init__(message, details={"cause": str(cause) if cause else None})
        self.__cause__ = cause
