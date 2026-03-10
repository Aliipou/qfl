"""Unit tests for EU AI Act audit logger."""

import uuid
from datetime import datetime, timedelta

import pytest

from api.schemas import AuditEvent, RiskLevel
from core.privacy.audit import AuditLogger


@pytest.fixture
def logger() -> AuditLogger:
    return AuditLogger()


class TestAuditLogger:
    def test_log_creates_entry(self, logger):
        entry = logger.log(event=AuditEvent.ROUND_STARTED)
        assert entry.event == AuditEvent.ROUND_STARTED
        assert entry.id is not None

    def test_log_with_all_fields(self, logger):
        rid = uuid.uuid4()
        entry = logger.log(
            event=AuditEvent.CLIENT_UPDATE_RECEIVED,
            round_id=rid,
            client_id="client_01",
            tenant_id="tenant_a",
            details={"num_samples": 500},
            risk_level=RiskLevel.HIGH,
        )
        assert entry.round_id == rid
        assert entry.client_id == "client_01"
        assert entry.tenant_id == "tenant_a"
        assert entry.details["num_samples"] == 500
        assert entry.risk_level == RiskLevel.HIGH

    def test_get_events_all(self, logger):
        logger.log(AuditEvent.ROUND_STARTED)
        logger.log(AuditEvent.ROUND_COMPLETED)
        events = logger.get_events()
        assert len(events) == 2

    def test_get_events_filter_tenant(self, logger):
        logger.log(AuditEvent.ROUND_STARTED, tenant_id="tenant_a")
        logger.log(AuditEvent.ROUND_STARTED, tenant_id="tenant_b")
        events = logger.get_events(tenant_id="tenant_a")
        assert len(events) == 1
        assert events[0].tenant_id == "tenant_a"

    def test_get_events_filter_round(self, logger):
        rid = uuid.uuid4()
        other_rid = uuid.uuid4()
        logger.log(AuditEvent.ROUND_STARTED, round_id=rid)
        logger.log(AuditEvent.ROUND_STARTED, round_id=other_rid)
        events = logger.get_events(round_id=rid)
        assert len(events) == 1
        assert events[0].round_id == rid

    def test_get_events_limit(self, logger):
        for i in range(10):
            logger.log(AuditEvent.CLIENT_JOINED, tenant_id="t1")
        events = logger.get_events(limit=3)
        assert len(events) == 3

    def test_get_events_sorted_newest_first(self, logger):
        logger.log(AuditEvent.ROUND_STARTED)
        logger.log(AuditEvent.ROUND_COMPLETED)
        events = logger.get_events()
        assert events[0].timestamp >= events[1].timestamp

    def test_generate_report_empty(self, logger):
        now = datetime.utcnow()
        report = logger.generate_report("tenant_x", now - timedelta(days=1), now)
        assert report.tenant_id == "tenant_x"
        assert report.total_rounds == 0
        assert report.total_dp_budget_consumed == 0.0
        assert report.gdpr_compliant is True

    def test_generate_report_counts_rounds(self, logger):
        rid = uuid.uuid4()
        logger.log(
            AuditEvent.ROUND_COMPLETED,
            round_id=rid,
            tenant_id="tenant_a",
            details={"dp_epsilon_used": 0.5},
        )
        logger.log(
            AuditEvent.ROUND_COMPLETED,
            round_id=uuid.uuid4(),
            tenant_id="tenant_a",
            details={"dp_epsilon_used": 0.3},
        )
        now = datetime.utcnow()
        report = logger.generate_report("tenant_a", now - timedelta(seconds=1), now + timedelta(seconds=1))
        assert report.total_rounds == 2
        assert abs(report.total_dp_budget_consumed - 0.8) < 1e-6

    def test_generate_report_no_dp_in_details(self, logger):
        """Round completed without dp_epsilon_used key → defaults to 0."""
        logger.log(
            AuditEvent.ROUND_COMPLETED,
            tenant_id="tenant_z",
            details={},
        )
        now = datetime.utcnow()
        report = logger.generate_report("tenant_z", now - timedelta(seconds=1), now + timedelta(seconds=1))
        assert report.total_dp_budget_consumed == 0.0
