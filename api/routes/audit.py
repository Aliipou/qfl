"""GET /audit — EU AI Act compliance report."""

from datetime import datetime, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query

from api.dependencies import get_audit_logger
from api.schemas import AuditLog, AuditReport, RiskLevel
from core.privacy.audit import AuditLogger

router = APIRouter(prefix="/audit", tags=["compliance"])


@router.get(
    "/report/{tenant_id}",
    response_model=AuditReport,
    summary="EU AI Act compliance report for a tenant",
)
async def get_audit_report(
    tenant_id: str,
    from_date: datetime = Query(default_factory=lambda: datetime.utcnow() - timedelta(days=30)),
    to_date: datetime = Query(default_factory=datetime.utcnow),
    audit_logger: AuditLogger = Depends(get_audit_logger),
) -> AuditReport:
    """
    Generate EU AI Act Article 9 compliance report.

    Returns immutable audit trail, DP budget consumption,
    GDPR compliance status, and risk classification.
    """
    return audit_logger.generate_report(tenant_id, from_date, to_date)


@router.get(
    "/events",
    response_model=list[AuditLog],
    summary="Stream audit log events",
)
async def get_audit_events(
    tenant_id: str | None = None,
    round_id: UUID | None = None,
    limit: int = Query(default=50, le=500),
    audit_logger: AuditLogger = Depends(get_audit_logger),
) -> list[AuditLog]:
    """Return audit log entries, filterable by tenant or round."""
    return audit_logger.get_events(
        tenant_id=tenant_id,
        round_id=round_id,
        limit=limit,
    )
