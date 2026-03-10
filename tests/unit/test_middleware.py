"""Unit tests for security middleware."""

import time

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.middleware import InMemoryRateLimiter, _rate_limiter


@pytest.fixture(scope="module")
def client():
    return TestClient(app)


class TestSecurityHeaders:
    def test_hsts_header(self, client):
        resp = client.get("/health")
        assert "Strict-Transport-Security" in resp.headers

    def test_x_frame_options(self, client):
        resp = client.get("/health")
        assert resp.headers.get("X-Frame-Options") == "DENY"

    def test_x_content_type_options(self, client):
        resp = client.get("/health")
        assert resp.headers.get("X-Content-Type-Options") == "nosniff"

    def test_csp_header_present(self, client):
        resp = client.get("/health")
        assert "Content-Security-Policy" in resp.headers

    def test_referrer_policy(self, client):
        resp = client.get("/health")
        assert "Referrer-Policy" in resp.headers


class TestRequestIDMiddleware:
    def test_request_id_in_response(self, client):
        resp = client.get("/health")
        assert "X-Request-ID" in resp.headers

    def test_custom_request_id_preserved(self, client):
        custom_id = "test-request-123"
        resp = client.get("/health", headers={"X-Request-ID": custom_id})
        assert resp.headers.get("X-Request-ID") == custom_id

    def test_auto_generated_request_id(self, client):
        resp = client.get("/health")
        rid = resp.headers.get("X-Request-ID")
        assert rid and len(rid) > 0


class TestInMemoryRateLimiter:
    def test_allows_requests_within_limit(self):
        limiter = InMemoryRateLimiter(max_requests=10, window_seconds=60)
        for i in range(10):
            allowed, remaining = limiter.is_allowed("test_key")
            assert allowed is True

    def test_blocks_when_limit_exceeded(self):
        limiter = InMemoryRateLimiter(max_requests=3, window_seconds=60)
        for _ in range(3):
            limiter.is_allowed("key1")
        allowed, remaining = limiter.is_allowed("key1")
        assert allowed is False
        assert remaining == 0

    def test_different_keys_independent(self):
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
        limiter.is_allowed("key_a")
        limiter.is_allowed("key_a")
        # key_a exhausted, key_b should still work
        allowed, _ = limiter.is_allowed("key_b")
        assert allowed is True

    def test_remaining_decrements(self):
        limiter = InMemoryRateLimiter(max_requests=5, window_seconds=60)
        _, r1 = limiter.is_allowed("key")
        _, r2 = limiter.is_allowed("key")
        assert r2 == r1 - 1

    def test_window_expiry(self):
        limiter = InMemoryRateLimiter(max_requests=2, window_seconds=1)
        limiter.is_allowed("expiry_key")
        limiter.is_allowed("expiry_key")
        # Block
        allowed, _ = limiter.is_allowed("expiry_key")
        assert allowed is False
        # Wait for window to expire
        time.sleep(1.1)
        allowed, _ = limiter.is_allowed("expiry_key")
        assert allowed is True
