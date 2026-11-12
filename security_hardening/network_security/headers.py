"""Enterprise Security Response Headers."""

from typing import Dict


def get_enterprise_security_headers() -> Dict[str, str]:
    """Returns production-grade HTTP response security headers (OWASP ASVS compliant)."""
    return {
        # Strict-Transport-Security (2 years + include subdomains + preload)
        "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
        # Clickjacking defense
        "X-Frame-Options": "DENY",
        # MIME type sniffing defense
        "X-Content-Type-Options": "nosniff",
        # Information disclosure via referrer
        "Referrer-Policy": "strict-origin-when-cross-origin",
        # Content Security Policy (strict API profile)
        "Content-Security-Policy": (
            "default-src 'none'; "
            "frame-ancestors 'none'; "
            "base-uri 'none'; "
            "form-action 'none';"
        ),
        # Permissions Policy (disable hardware peripherals on API domain)
        "Permissions-Policy": (
            "accelerometer=(), "
            "camera=(), "
            "geolocation=(), "
            "gyroscope=(), "
            "magnetometer=(), "
            "microphone=(), "
            "payment=(), "
            "usb=()"
        ),
        # Cross-Origin Policies
        "Cross-Origin-Opener-Policy": "same-origin",
        "Cross-Origin-Resource-Policy": "same-origin",
    }


def get_financial_cache_control_headers() -> Dict[str, str]:
    """Cache prevention headers for sensitive financial and identity responses."""
    return {
        "Cache-Control": "no-store, no-cache, must-revalidate, private",
        "Pragma": "no-cache",
        "Expires": "0",
    }

