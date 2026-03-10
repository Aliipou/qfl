"""Pydantic v2 schemas for QFL Platform API."""

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class RoundStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    AGGREGATING = "aggregating"
    COMPLETED = "completed"
    FAILED = "failed"


class AggregationMethod(str, Enum):
    FED_AVG = "fed_avg"
    Q_FED_AVG = "q_fed_avg"


class RiskLevel(str, Enum):
    """EU AI Act Article 9 risk classification."""
    MINIMAL = "minimal"
    LIMITED = "limited"
    HIGH = "high"
    UNACCEPTABLE = "unacceptable"


# ---------------------------------------------------------------------------
# FL Round
# ---------------------------------------------------------------------------

class FLRoundConfig(BaseModel):
    """Configuration for a federated learning round."""
    num_clients: int = Field(default=3, ge=1, le=100)
    local_epochs: int = Field(default=5, ge=1, le=100)
    learning_rate: float = Field(default=0.01, gt=0, le=1.0)
    aggregation: AggregationMethod = AggregationMethod.FED_AVG
    dp_epsilon: float = Field(default=1.0, gt=0, description="Differential privacy epsilon")
    dp_delta: float = Field(default=1e-5, gt=0, description="Differential privacy delta")
    use_quantum: bool = Field(default=False, description="Enable quantum circuit components")


class FLRoundCreate(BaseModel):
    config: FLRoundConfig = Field(default_factory=FLRoundConfig)
    dataset: str = Field(default="mnist", description="Dataset identifier")
    model_architecture: str = Field(default="simple_cnn")


class FLRound(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    status: RoundStatus = RoundStatus.PENDING
    config: FLRoundConfig
    dataset: str
    model_architecture: str
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    global_accuracy: float | None = None
    privacy_budget_used: float | None = None
    num_clients_participated: int = 0

    model_config = {"from_attributes": True}


# ---------------------------------------------------------------------------
# Client Update
# ---------------------------------------------------------------------------

class ClientUpdate(BaseModel):
    """Model weight update from a single FL client."""
    client_id: str
    round_id: UUID
    tenant_id: str
    weights_hash: str = Field(description="SHA-256 of serialized weight tensor")
    num_samples: int = Field(gt=0)
    local_loss: float
    local_accuracy: float
    dp_noise_applied: bool = False
    qkd_key_id: str | None = Field(default=None, description="QKD key used for encryption")
    submitted_at: datetime = Field(default_factory=datetime.utcnow)


class ClientUpdateAck(BaseModel):
    round_id: UUID
    client_id: str
    accepted: bool
    message: str = ""


# ---------------------------------------------------------------------------
# Audit Log
# ---------------------------------------------------------------------------

class AuditEvent(str, Enum):
    ROUND_STARTED = "round_started"
    CLIENT_JOINED = "client_joined"
    CLIENT_UPDATE_RECEIVED = "client_update_received"
    AGGREGATION_COMPLETED = "aggregation_completed"
    ROUND_COMPLETED = "round_completed"
    ROUND_FAILED = "round_failed"
    DP_BUDGET_CONSUMED = "dp_budget_consumed"
    MODEL_DEPLOYED = "model_deployed"
    ERASURE_REQUEST = "erasure_request"


class AuditLog(BaseModel):
    """Immutable EU AI Act audit trail entry."""
    id: UUID = Field(default_factory=uuid4)
    event: AuditEvent
    round_id: UUID | None = None
    client_id: str | None = None
    tenant_id: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    details: dict[str, Any] = Field(default_factory=dict)
    risk_level: RiskLevel = RiskLevel.LIMITED
    model_card_ref: str | None = None

    model_config = {"from_attributes": True}


class AuditReport(BaseModel):
    """EU AI Act compliance report."""
    tenant_id: str
    from_date: datetime
    to_date: datetime
    total_rounds: int
    total_dp_budget_consumed: float
    events: list[AuditLog]
    risk_classification: RiskLevel
    gdpr_compliant: bool
    technical_doc_ref: str | None = None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

class HealthResponse(BaseModel):
    status: str = "ok"
    version: str = "0.1.0"
    quantum_backend: str = "aer_simulator"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
