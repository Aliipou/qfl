"""EU AI Act Article 9 audit trail logger."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import UUID

from api.schemas import AuditEvent, AuditLog, AuditReport, RiskLevel


class AuditLogger:
    """
    Immutable in-memory audit logger (Phase 1).

    Phase 5 will persist to PostgreSQL with append-only rows.
    """

    def __init__(self) -> None:
        self._events: list[AuditLog] = []

    def log(
        self,
        event: AuditEvent,
        round_id: Optional[UUID] = None,
        client_id: Optional[str] = None,
        tenant_id: Optional[str] = None,
        details: Optional[dict[str, Any]] = None,
        risk_level: RiskLevel = RiskLevel.LIMITED,
    ) -> AuditLog:
        entry = AuditLog(
            event=event,
            round_id=round_id,
            client_id=client_id,
            tenant_id=tenant_id,
            details=details or {},
            risk_level=risk_level,
        )
        self._events.append(entry)
        return entry

    def get_events(
        self,
        tenant_id: Optional[str] = None,
        round_id: Optional[UUID] = None,
        limit: int = 50,
    ) -> list[AuditLog]:
        events = self._events
        if tenant_id:
            events = [e for e in events if e.tenant_id == tenant_id]
        if round_id:
            events = [e for e in events if e.round_id == round_id]
        return sorted(events, key=lambda e: e.timestamp, reverse=True)[:limit]

    def generate_report(
        self,
        tenant_id: str,
        from_date: datetime,
        to_date: datetime,
    ) -> AuditReport:
        events = [
            e
            for e in self._events
            if (e.tenant_id == tenant_id or e.tenant_id is None)
            and from_date <= e.timestamp <= to_date
        ]

        # Sum DP budget from completed round events
        dp_used = sum(
            e.details.get("dp_epsilon_used", 0.0)
            for e in events
            if e.event == AuditEvent.ROUND_COMPLETED
        )
        total_rounds = sum(
            1 for e in events if e.event == AuditEvent.ROUND_COMPLETED
        )

        return AuditReport(
            tenant_id=tenant_id,
            from_date=from_date,
            to_date=to_date,
            total_rounds=total_rounds,
            total_dp_budget_consumed=dp_used,
            events=events,
            risk_classification=RiskLevel.LIMITED,
            gdpr_compliant=True,
        )
