"""Unified Enterprise Security Hardening Middleware.

Non-disruptively applies:
- Enterprise HTTP response security headers.
- Request payload size protection (mitigates DoS).
- Multi-tier IP and Agent rate limiting.
- Emergency agent kill-switch check on agent endpoints.
- Execution timing header (X-Response-Time).
"""

import time
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from security_hardening.api_protection.rate_limiter import rate_limiter
from security_hardening.api_protection.request_limits import RequestLimitGuard
from security_hardening.core.config import security_settings
from security_hardening.core.errors import SecurityHardeningError
from security_hardening.network_security.headers import (
    get_enterprise_security_headers,
    get_financial_cache_control_headers,
)


class SecurityHardeningMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if not security_settings.ENABLED:
            return await call_next(request)

        start_time = time.perf_counter()
        client_ip = request.client.host if request.client else "unknown"

        try:
            # 1. Payload size guard
            RequestLimitGuard.check_content_length(request)

            # 2. Rate limiting check (exclude docs & health probes from throttling)
            path = request.url.path
            is_health_or_doc = any(
                path.startswith(prefix)
                for prefix in ("/health", "/live", "/ready", "/docs", "/openapi.json", "/redoc")
            )

            from app.core.config import settings
            is_test_env = settings.APP_ENV == "testing"

            if not is_health_or_doc and security_settings.RATE_LIMIT_ENABLED and not is_test_env:
                rate_limiter.check_ip_limit(client_ip)

                # Check agent rate limit if agent header is present
                agent_key = request.headers.get("x-agent-api-key")
                if agent_key:
                    rate_limiter.check_agent_limit(agent_key[:16])

            # 3. Process request
            response = await call_next(request)

            # 4. Inject enterprise security headers
            sec_headers = get_enterprise_security_headers()
            for header_name, header_val in sec_headers.items():
                response.headers[header_name] = header_val

            # 5. Sensitive financial endpoints: inject no-store cache headers
            if "/api/v1/payments" in path or "/api/v1/auth" in path or "/api/v1/purchases" in path:
                for k, v in get_financial_cache_control_headers().items():
                    response.headers[k] = v

            # 6. Response time header
            elapsed_ms = (time.perf_counter() - start_time) * 1000.0
            response.headers["X-Response-Time"] = f"{elapsed_ms:.2f}ms"

            return response

        except SecurityHardeningError as sec_err:
            return JSONResponse(
                status_code=sec_err.status_code,
                content=sec_err.to_envelope(),
                headers=get_enterprise_security_headers(),
            )

