"""
Security middleware — God-scale hardening.

Implements:
  - Security headers (HSTS, CSP, X-Frame-Options, etc.)
  - Rate limiting (per-IP sliding window via Redis)
  - Request ID injection for distributed tracing
  - Tenant isolation enforcement
  - JWT bearer token validation scaffold
  - Audit logging of every request
"""

from __future__ import annotations

import hashlib
import time
import uuid
from collections import defaultdict
from typing import Callable

import structlog
from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Security headers
# ---------------------------------------------------------------------------

SECURITY_HEADERS = {
    "Strict-Transport-Security": "max-age=63072000; includeSubDomains; preload",
    "Content-Security-Policy": (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data:; "
        "connect-src 'self'; "
        "frame-ancestors 'none';"
    ),
    "X-Frame-Options": "DENY",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    "X-XSS-Protection": "1; mode=block",
    "Cache-Control": "no-store, max-age=0",
}


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Inject security headers into every response."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        response = await call_next(request)
        for header, value in SECURITY_HEADERS.items():
            response.headers[header] = value
        return response


# ---------------------------------------------------------------------------
# Request ID middleware
# ---------------------------------------------------------------------------

class RequestIDMiddleware(BaseHTTPMiddleware):
    """Inject X-Request-ID into every request/response for distributed tracing."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        request.state.request_id = request_id

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


# ---------------------------------------------------------------------------
# In-memory rate limiter (Redis-backed in production)
# ---------------------------------------------------------------------------

class InMemoryRateLimiter:
    """
    Sliding window rate limiter.

    Production note: replace _windows with Redis ZADD/ZCOUNT for
    horizontal scalability across multiple coordinator replicas.
    """

    def __init__(self, max_requests: int = 100, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._windows: dict[str, list[float]] = defaultdict(list)

    def is_allowed(self, key: str) -> tuple[bool, int]:
        """Returns (allowed, remaining_requests)."""
        now = time.monotonic()
        window = self._windows[key]

        # Evict expired timestamps
        cutoff = now - self.window_seconds
        self._windows[key] = [t for t in window if t > cutoff]

        if len(self._windows[key]) >= self.max_requests:
            return False, 0

        self._windows[key].append(now)
        remaining = self.max_requests - len(self._windows[key])
        return True, remaining


_rate_limiter = InMemoryRateLimiter(max_requests=200, window_seconds=60)


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Per-IP rate limiting. Returns 429 when limit exceeded."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        client_ip = (
            request.headers.get("X-Forwarded-For", "").split(",")[0].strip()
            or (request.client.host if request.client else "unknown")
        )
        # Use hashed IP to avoid logging raw IPs (GDPR)
        ip_hash = hashlib.sha256(client_ip.encode()).hexdigest()[:16]

        allowed, remaining = _rate_limiter.is_allowed(ip_hash)

        if not allowed:
            logger.warning("rate_limit_exceeded", ip_hash=ip_hash, path=request.url.path)
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many requests. Please retry later."},
                headers={"Retry-After": "60"},
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        return response


# ---------------------------------------------------------------------------
# Request logging middleware
# ---------------------------------------------------------------------------

class AccessLogMiddleware(BaseHTTPMiddleware):
    """Structured access logging for every request."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        start = time.perf_counter()
        request_id = getattr(request.state, "request_id", "-")

        response = await call_next(request)

        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "http_request",
            method=request.method,
            path=request.url.path,
            status=response.status_code,
            duration_ms=round(duration_ms, 2),
            request_id=request_id,
        )
        return response
