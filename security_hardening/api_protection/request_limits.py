"""Request size limits and execution timeout enforcement."""

from typing import Optional
from starlette.requests import Request
from security_hardening.core.config import security_settings
from security_hardening.core.errors import PayloadTooLargeError


class RequestLimitGuard:
    @staticmethod
    def check_content_length(request: Request, max_bytes: Optional[int] = None) -> None:
        """Validate Content-Length header before reading full body into memory."""
        limit = max_bytes or security_settings.MAX_REQUEST_BODY_BYTES
        content_length_header = request.headers.get("content-length")
        if content_length_header:
            try:
                length = int(content_length_header)
                if length > limit:
                    raise PayloadTooLargeError(max_bytes=limit, received_bytes=length)
            except ValueError:
                pass

    @staticmethod
    def enforce_body_size(body_bytes: bytes, max_bytes: Optional[int] = None) -> None:
        """Verify actual body byte count."""
        limit = max_bytes or security_settings.MAX_REQUEST_BODY_BYTES
        if len(body_bytes) > limit:
            raise PayloadTooLargeError(max_bytes=limit, received_bytes=len(body_bytes))

