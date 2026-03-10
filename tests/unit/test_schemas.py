"""Unit tests for Pydantic schemas — covers all models and enums."""

import uuid
from datetime import datetime

import pytest
from pydantic import ValidationError

from api.schemas import (
    AggregationMethod,
    AuditEvent,
    AuditLog,
    AuditReport,
    ClientUpdate,
    ClientUpdateAck,
    FLRound,
    FLRoundConfig,
    FLRoundCreate,
    HealthResponse,
    RiskLevel,
    RoundStatus,
)


class TestFLRoundConfig:
    def test_defaults(self):
        c = FLRoundConfig()
        assert c.num_clients == 3
        assert c.local_epochs == 5
        assert c.aggregation == AggregationMethod.FED_AVG
        assert c.use_quantum is False

    def test_valid_custom(self):
        c = FLRoundConfig(num_clients=10, learning_rate=0.001, use_quantum=True)
        assert c.num_clients == 10
        assert c.learning_rate == 0.001

    def test_num_clients_min(self):
        with pytest.raises(ValidationError):
            FLRoundConfig(num_clients=0)

    def test_num_clients_max(self):
        with pytest.raises(ValidationError):
            FLRoundConfig(num_clients=101)

    def test_learning_rate_bounds(self):
        with pytest.raises(ValidationError):
            FLRoundConfig(learning_rate=0.0)
        with pytest.raises(ValidationError):
            FLRoundConfig(learning_rate=1.1)

    def test_q_fed_avg_config(self):
        c = FLRoundConfig(aggregation=AggregationMethod.Q_FED_AVG)
        assert c.aggregation == AggregationMethod.Q_FED_AVG

    def test_model_dump(self):
        c = FLRoundConfig()
        d = c.model_dump()
        assert "num_clients" in d
        assert "dp_epsilon" in d


class TestFLRoundCreate:
    def test_defaults(self):
        p = FLRoundCreate()
        assert p.dataset == "mnist"
        assert p.model_architecture == "simple_cnn"

    def test_custom(self):
        p = FLRoundCreate(dataset="cifar10", model_architecture="resnet18")
        assert p.dataset == "cifar10"


class TestFLRound:
    def test_creation(self):
        r = FLRound(
            config=FLRoundConfig(),
            dataset="mnist",
            model_architecture="simple_cnn",
        )
        assert r.status == RoundStatus.PENDING
        assert r.id is not None
        assert r.created_at is not None
        assert r.started_at is None
        assert r.completed_at is None
        assert r.global_accuracy is None
        assert r.num_clients_participated == 0


class TestClientUpdate:
    def test_valid(self):
        rid = uuid.uuid4()
        u = ClientUpdate(
            client_id="client_01",
            round_id=rid,
            tenant_id="tenant_a",
            weights_hash="x" * 64,
            num_samples=500,
            local_loss=0.4,
            local_accuracy=0.85,
        )
        assert u.dp_noise_applied is False
        assert u.qkd_key_id is None

    def test_invalid_num_samples(self):
        with pytest.raises(ValidationError):
            ClientUpdate(
                client_id="c",
                round_id=uuid.uuid4(),
                tenant_id="t",
                weights_hash="x",
                num_samples=0,
                local_loss=0.1,
                local_accuracy=0.9,
            )


class TestClientUpdateAck:
    def test_accepted(self):
        ack = ClientUpdateAck(
            round_id=uuid.uuid4(),
            client_id="c01",
            accepted=True,
            message="OK",
        )
        assert ack.accepted is True

    def test_default_message(self):
        ack = ClientUpdateAck(round_id=uuid.uuid4(), client_id="c", accepted=False)
        assert ack.message == ""


class TestAuditLog:
    def test_creation(self):
        log = AuditLog(event=AuditEvent.ROUND_STARTED)
        assert log.id is not None
        assert log.timestamp is not None
        assert log.risk_level == RiskLevel.LIMITED

    def test_all_events_valid(self):
        for event in AuditEvent:
            log = AuditLog(event=event)
            assert log.event == event


class TestHealthResponse:
    def test_defaults(self):
        h = HealthResponse()
        assert h.status == "ok"
        assert h.version == "0.1.0"
        assert h.quantum_backend == "aer_simulator"
        assert isinstance(h.timestamp, datetime)


class TestEnums:
    def test_round_status_values(self):
        assert RoundStatus.PENDING == "pending"
        assert RoundStatus.RUNNING == "running"
        assert RoundStatus.AGGREGATING == "aggregating"
        assert RoundStatus.COMPLETED == "completed"
        assert RoundStatus.FAILED == "failed"

    def test_aggregation_method_values(self):
        assert AggregationMethod.FED_AVG == "fed_avg"
        assert AggregationMethod.Q_FED_AVG == "q_fed_avg"

    def test_risk_level_values(self):
        assert RiskLevel.MINIMAL == "minimal"
        assert RiskLevel.LIMITED == "limited"
        assert RiskLevel.HIGH == "high"
        assert RiskLevel.UNACCEPTABLE == "unacceptable"

    def test_audit_event_values(self):
        assert AuditEvent.ROUND_STARTED == "round_started"
        assert AuditEvent.ERASURE_REQUEST == "erasure_request"
