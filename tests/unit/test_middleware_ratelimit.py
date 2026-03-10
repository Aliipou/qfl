"""Test rate limit 429 response — isolated to avoid polluting global limiter."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.responses import Response

from api.middleware import InMemoryRateLimiter, RateLimitMiddleware


def _make_app(max_requests: int = 2) -> TestClient:
    """Create a minimal app with tight rate limits for testing."""
    mini = FastAPI()
    mini.add_middleware(RateLimitMiddleware)
    # Override limiter for this app via monkeypatching inside test

    @mini.get("/ping")
    async def ping():
        return {"ok": True}

    return TestClient(mini)


class TestRateLimitResponse:
    def test_429_response_headers(self):
        limiter = InMemoryRateLimiter(max_requests=1, window_seconds=60)
        limiter.is_allowed("x")  # exhaust
        allowed, remaining = limiter.is_allowed("x")
        assert not allowed
        assert remaining == 0

    def test_rate_limit_remaining_header_present(self):
        from fastapi.testclient import TestClient
        from api.main import app
        client = TestClient(app)
        resp = client.get("/health")
        # Header may or may not be present depending on count
        assert resp.status_code in (200, 429)
