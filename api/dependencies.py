"""Shared application dependencies (singletons)."""

from core.federated.coordinator import FLCoordinator
from core.privacy.audit import AuditLogger

# Single audit logger instance shared by coordinator and routes
_audit_logger = AuditLogger()
_coordinator = FLCoordinator(audit_logger=_audit_logger)


def get_coordinator() -> FLCoordinator:
    return _coordinator


def get_audit_logger() -> AuditLogger:
    return _audit_logger
