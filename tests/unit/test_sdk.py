"""Unit tests for QFL Python SDK client."""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from sdk.qfl_client.client import QFLClient
from sdk.qfl_client import QFLClient as QFLClientImport, __version__


@pytest.fixture
def sdk_client() -> QFLClient:
    """SDK client wired to the in-process FastAPI test app."""
    transport = MagicMock()

    # Use real httpx transport against TestClient
    test_app = TestClient(app)

    class _MockHttpxClient:
        def __init__(self, *a, **kw):
            self._tc = TestClient(app)

        def get(self, path, **kwargs):
            params = kwargs.get("params", {})
            return self._tc.get(path, params=params)

        def post(self, path, **kwargs):
            return self._tc.post(path, json=kwargs.get("json"))

        def close(self):
            pass

    client = QFLClient(base_url="http://test", tenant_id="tenant_sdk")
    client._client = _MockHttpxClient()
    return client


class TestSDKImport:
    def test_version_string(self):
        assert __version__ == "0.1.0"

    def test_exported_class(self):
        assert QFLClientImport is QFLClient


class TestQFLClientInit:
    def test_defaults(self):
        c = QFLClient()
        assert c.base_url == "http://localhost:8000"
        assert c.tenant_id == "default"
        c.close()

    def test_trailing_slash_stripped(self):
        c = QFLClient(base_url="http://example.com/")
        assert c.base_url == "http://example.com"
        c.close()

    def test_api_key_sets_auth_header(self):
        c = QFLClient(api_key="secret")
        assert "Authorization" in c._client.headers
        c.close()

    def test_context_manager(self):
        with QFLClient() as c:
            assert c is not None


class TestSDKHealth:
    def test_health(self, sdk_client):
        data = sdk_client.health()
        assert data["status"] == "ok"


class TestSDKTraining:
    def test_start_round(self, sdk_client):
        data = sdk_client.start_round(num_clients=2)
        assert "id" in data
        assert data["status"] == "pending"

    def test_start_round_quantum(self, sdk_client):
        data = sdk_client.start_round(
            num_clients=1,
            aggregation="q_fed_avg",
            use_quantum=True,
            dp_epsilon=0.5,
        )
        assert data["config"]["use_quantum"] is True

    def test_submit_update(self, sdk_client):
        round_data = sdk_client.start_round(num_clients=1)
        round_id = round_data["id"]
        ack = sdk_client.submit_update(
            round_id=round_id,
            weights_hash="a" * 64,
            num_samples=500,
            local_loss=0.3,
            local_accuracy=0.9,
            dp_noise_applied=True,
            qkd_key_id="key_0001",
        )
        assert ack["accepted"] is True

    def test_submit_update_uuid_object(self, sdk_client):
        round_data = sdk_client.start_round(num_clients=1)
        round_id = uuid.UUID(round_data["id"])
        ack = sdk_client.submit_update(
            round_id=round_id,
            weights_hash="b" * 64,
            num_samples=200,
            local_loss=0.5,
            local_accuracy=0.7,
        )
        assert ack["accepted"] is True


class TestSDKStatus:
    def test_get_round(self, sdk_client):
        r = sdk_client.start_round()
        data = sdk_client.get_round(r["id"])
        assert data["id"] == r["id"]

    def test_list_rounds(self, sdk_client):
        sdk_client.start_round()
        rounds = sdk_client.list_rounds(limit=5)
        assert isinstance(rounds, list)


class TestSDKAudit:
    def test_audit_report(self, sdk_client):
        report = sdk_client.audit_report()
        assert "tenant_id" in report
        assert "gdpr_compliant" in report

    def test_audit_report_custom_tenant(self, sdk_client):
        report = sdk_client.audit_report(tenant_id="tenant_a")
        assert report["tenant_id"] == "tenant_a"

    def test_audit_events(self, sdk_client):
        events = sdk_client.audit_events()
        assert isinstance(events, list)

    def test_audit_events_with_round_id(self, sdk_client):
        r = sdk_client.start_round()
        events = sdk_client.audit_events(round_id=r["id"])
        assert isinstance(events, list)
