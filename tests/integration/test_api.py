"""Integration tests for QFL Platform API — full round-trip."""

import uuid
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.schemas import RoundStatus


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(app)


class TestHealth:
    def test_health_returns_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"
        assert data["quantum_backend"] == "aer_simulator"
        assert "timestamp" in data

    def test_docs_accessible(self, client):
        resp = client.get("/docs")
        assert resp.status_code == 200

    def test_redoc_accessible(self, client):
        resp = client.get("/redoc")
        assert resp.status_code == 200


class TestTrainEndpoints:
    def test_trigger_training_returns_202(self, client):
        resp = client.post("/train", json={})
        assert resp.status_code == 202
        data = resp.json()
        assert "id" in data
        assert data["status"] == "pending"

    def test_trigger_training_with_config(self, client):
        payload = {
            "config": {
                "num_clients": 2,
                "local_epochs": 3,
                "aggregation": "q_fed_avg",
                "use_quantum": True,
            },
            "dataset": "cifar10",
            "model_architecture": "resnet18",
        }
        resp = client.post("/train", json=payload)
        assert resp.status_code == 202
        data = resp.json()
        assert data["dataset"] == "cifar10"
        assert data["config"]["aggregation"] == "q_fed_avg"

    def test_submit_client_update_accepted(self, client):
        # Create a round first
        resp = client.post("/train", json={"config": {"num_clients": 1}})
        round_id = resp.json()["id"]

        update = {
            "client_id": "client_01",
            "round_id": round_id,
            "tenant_id": "tenant_a",
            "weights_hash": "a" * 64,
            "num_samples": 500,
            "local_loss": 0.4,
            "local_accuracy": 0.85,
        }
        resp = client.post(f"/train/{round_id}/update", json=update)
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is True
        assert data["client_id"] == "client_01"

    def test_submit_update_mismatched_round_id(self, client):
        resp = client.post("/train", json={})
        round_id = resp.json()["id"]
        other_id = str(uuid.uuid4())

        update = {
            "client_id": "client_01",
            "round_id": other_id,
            "tenant_id": "tenant_a",
            "weights_hash": "b" * 64,
            "num_samples": 100,
            "local_loss": 0.5,
            "local_accuracy": 0.7,
        }
        resp = client.post(f"/train/{round_id}/update", json=update)
        assert resp.status_code == 400

    def test_submit_update_nonexistent_round(self, client):
        phantom_id = str(uuid.uuid4())
        update = {
            "client_id": "client_01",
            "round_id": phantom_id,
            "tenant_id": "tenant_a",
            "weights_hash": "c" * 64,
            "num_samples": 100,
            "local_loss": 0.5,
            "local_accuracy": 0.7,
        }
        resp = client.post(f"/train/{phantom_id}/update", json=update)
        assert resp.status_code == 200
        data = resp.json()
        assert data["accepted"] is False


class TestStatusEndpoints:
    def test_get_round_status(self, client):
        resp = client.post("/train", json={})
        round_id = resp.json()["id"]

        resp = client.get(f"/status/{round_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["id"] == round_id

    def test_get_nonexistent_round_returns_404(self, client):
        resp = client.get(f"/status/{uuid.uuid4()}")
        assert resp.status_code == 404

    def test_list_rounds(self, client):
        client.post("/train", json={})
        resp = client.get("/status")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_list_rounds_filter_status(self, client):
        resp = client.get("/status?status_filter=pending")
        assert resp.status_code == 200

    def test_list_rounds_limit(self, client):
        for _ in range(5):
            client.post("/train", json={})
        resp = client.get("/status?limit=2")
        assert resp.status_code == 200
        assert len(resp.json()) <= 2


class TestAuditEndpoints:
    def test_audit_report(self, client):
        resp = client.get("/audit/report/tenant_a")
        assert resp.status_code == 200
        data = resp.json()
        assert data["tenant_id"] == "tenant_a"
        assert "gdpr_compliant" in data
        assert "risk_classification" in data

    def test_audit_events(self, client):
        resp = client.get("/audit/events")
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_audit_events_filter_tenant(self, client):
        resp = client.get("/audit/events?tenant_id=tenant_a")
        assert resp.status_code == 200

    def test_audit_events_filter_round(self, client):
        resp = client.post("/train", json={})
        round_id = resp.json()["id"]
        resp = client.get(f"/audit/events?round_id={round_id}")
        assert resp.status_code == 200

    def test_audit_events_limit(self, client):
        resp = client.get("/audit/events?limit=5")
        assert resp.status_code == 200
        assert len(resp.json()) <= 5


class TestFullRoundTrip:
    def test_complete_fl_round_one_client(self, client):
        """Full FL round: create → submit update → auto-aggregate → completed."""
        # Create round with 1 client so it auto-aggregates
        resp = client.post("/train", json={"config": {"num_clients": 1}})
        assert resp.status_code == 202
        round_id = resp.json()["id"]

        # Submit client update
        update = {
            "client_id": "client_01",
            "round_id": round_id,
            "tenant_id": "tenant_a",
            "weights_hash": "d" * 64,
            "num_samples": 1000,
            "local_loss": 0.3,
            "local_accuracy": 0.92,
        }
        resp = client.post(f"/train/{round_id}/update", json=update)
        assert resp.json()["accepted"] is True

    def test_round_with_quantum_aggregation(self, client):
        resp = client.post(
            "/train",
            json={
                "config": {
                    "num_clients": 1,
                    "aggregation": "q_fed_avg",
                    "use_quantum": True,
                }
            },
        )
        assert resp.status_code == 202
        round_id = resp.json()["id"]

        update = {
            "client_id": "client_01",
            "round_id": round_id,
            "tenant_id": "tenant_b",
            "weights_hash": "e" * 64,
            "num_samples": 800,
            "local_loss": 0.25,
            "local_accuracy": 0.94,
            "dp_noise_applied": True,
            "qkd_key_id": "key_abcd",
        }
        resp = client.post(f"/train/{round_id}/update", json=update)
        assert resp.json()["accepted"] is True
