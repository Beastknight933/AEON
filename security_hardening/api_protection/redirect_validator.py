"""Open-Redirect Protection and Return URL Validator."""

from typing import List, Optional
from urllib.parse import urlparse
from security_hardening.core.errors import SecurityHardeningError


class OpenRedirectError(SecurityHardeningError):
    def __init__(self, target_url: str):
        super().__init__(
            message=f"Redirect destination '{target_url}' is not in the permitted domain allowlist.",
            code="UNAUTHORIZED_REDIRECT_TARGET",
            details={"target_url": target_url},
            status_code=400,
        )


class RedirectValidator:
    DEFAULT_ALLOWED_DOMAINS = [
        "aeon-control.vercel.app",
        "localhost",
        "127.0.0.1",
        "sandbox.paypal.com",
        "paypal.com",
    ]

    @classmethod
    def validate_redirect_url(cls, url: str, extra_allowed_domains: Optional[List[str]] = None) -> None:
        """Verify that redirect URL target belongs to an explicitly allowed domain."""
        if not url:
            return

        parsed = urlparse(url)
        # Relative URLs are safe within the same origin
        if not parsed.netloc and url.startswith("/"):
            return

        allowed = cls.DEFAULT_ALLOWED_DOMAINS + (extra_allowed_domains or [])
        target_domain = parsed.hostname.lower() if parsed.hostname else ""

        is_allowed = any(
            target_domain == domain.lower() or target_domain.endswith(f".{domain.lower()}")
            for domain in allowed
        )

        if not is_allowed:
            raise OpenRedirectError(url)

