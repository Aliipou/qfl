"""FL Coordinator — manages rounds, collects client updates, triggers aggregation."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

import numpy as np

from api.schemas import (
    AggregationMethod,
    AuditEvent,
    ClientUpdate,
    ClientUpdateAck,
    FLRound,
    FLRoundCreate,
    RoundStatus,
)
from core.federated.aggregation import fed_avg, q_fed_avg
from core.privacy.audit import AuditLogger  # noqa: F401 — re-exported for DI

logger = logging.getLogger(__name__)


class FLCoordinator:
    """
    In-memory FL coordinator (Phase 1).

    Phase 4 will replace the in-memory store with Redis + PostgreSQL.
    """

    def __init__(self, audit_logger: AuditLogger | None = None) -> None:
        self._rounds: dict[UUID, FLRound] = {}
        self._client_updates: dict[UUID, list[ClientUpdate]] = {}
        self._audit = audit_logger if audit_logger is not None else AuditLogger()

    # ------------------------------------------------------------------
    # Round management
    # ------------------------------------------------------------------

    def create_round(self, payload: FLRoundCreate) -> FLRound:
        fl_round = FLRound(
            config=payload.config,
            dataset=payload.dataset,
            model_architecture=payload.model_architecture,
        )
        self._rounds[fl_round.id] = fl_round
        self._client_updates[fl_round.id] = []
        self._audit.log(
            event=AuditEvent.ROUND_STARTED,
            round_id=fl_round.id,
            details={"config": payload.config.model_dump()},
        )
        logger.info("Created FL round %s", fl_round.id)
        return fl_round

    def get_round(self, round_id: UUID) -> Optional[FLRound]:
        return self._rounds.get(round_id)

    def list_rounds(
        self,
        limit: int = 20,
        status_filter: RoundStatus | None = None,
    ) -> list[FLRound]:
        rounds = list(self._rounds.values())
        if status_filter:
            rounds = [r for r in rounds if r.status == status_filter]
        return sorted(rounds, key=lambda r: r.created_at, reverse=True)[:limit]

    # ------------------------------------------------------------------
    # Client updates
    # ------------------------------------------------------------------

    async def accept_client_update(self, update: ClientUpdate) -> ClientUpdateAck:
        fl_round = self._rounds.get(update.round_id)
        if fl_round is None:
            return ClientUpdateAck(
                round_id=update.round_id,
                client_id=update.client_id,
                accepted=False,
                message="Round not found",
            )
        if fl_round.status not in (RoundStatus.PENDING, RoundStatus.RUNNING):
            return ClientUpdateAck(
                round_id=update.round_id,
                client_id=update.client_id,
                accepted=False,
                message=f"Round is {fl_round.status}, not accepting updates",
            )

        fl_round.status = RoundStatus.RUNNING
        fl_round.started_at = fl_round.started_at or datetime.utcnow()
        self._client_updates[update.round_id].append(update)
        fl_round.num_clients_participated = len(self._client_updates[update.round_id])

        self._audit.log(
            event=AuditEvent.CLIENT_UPDATE_RECEIVED,
            round_id=update.round_id,
            client_id=update.client_id,
            tenant_id=update.tenant_id,
            details={"num_samples": update.num_samples, "local_loss": update.local_loss},
        )
        logger.info(
            "Round %s: accepted update from client %s (%d/%d)",
            update.round_id,
            update.client_id,
            fl_round.num_clients_participated,
            fl_round.config.num_clients,
        )

        # Auto-aggregate when all clients have submitted
        if fl_round.num_clients_participated >= fl_round.config.num_clients:
            asyncio.create_task(self._aggregate(update.round_id))

        return ClientUpdateAck(
            round_id=update.round_id,
            client_id=update.client_id,
            accepted=True,
            message="Update accepted",
        )

    # ------------------------------------------------------------------
    # Aggregation
    # ------------------------------------------------------------------

    async def run_round(self, round_id: UUID) -> None:
        """Background task: waits for clients then aggregates."""
        fl_round = self._rounds.get(round_id)
        if fl_round is None:
            return
        # In production this would wait for a timeout / enough clients.
        # Phase 1: immediate stub for background task wiring.
        logger.info("Round %s background task started", round_id)

    async def _aggregate(self, round_id: UUID) -> None:
        fl_round = self._rounds.get(round_id)
        if fl_round is None:
            return

        fl_round.status = RoundStatus.AGGREGATING
        updates = self._client_updates[round_id]

        try:
            # Simulate weight arrays (real weights arrive in Phase 3)
            mock_weights = [
                [np.random.randn(10, 10).astype(np.float32)] for _ in updates
            ]
            num_samples = [u.num_samples for u in updates]

            if fl_round.config.aggregation == AggregationMethod.Q_FED_AVG:
                _ = q_fed_avg(mock_weights, num_samples)
            else:
                _ = fed_avg(mock_weights, num_samples)

            # Simulate accuracy metric
            fl_round.global_accuracy = float(
                np.mean([u.local_accuracy for u in updates])
            )
            fl_round.privacy_budget_used = fl_round.config.dp_epsilon
            fl_round.status = RoundStatus.COMPLETED
            fl_round.completed_at = datetime.utcnow()

            self._audit.log(
                event=AuditEvent.ROUND_COMPLETED,
                round_id=round_id,
                details={
                    "global_accuracy": fl_round.global_accuracy,
                    "dp_epsilon_used": fl_round.privacy_budget_used,
                    "clients": len(updates),
                },
            )
            logger.info("Round %s completed. Accuracy=%.4f", round_id, fl_round.global_accuracy)

        except Exception as exc:
            fl_round.status = RoundStatus.FAILED
            self._audit.log(
                event=AuditEvent.ROUND_FAILED,
                round_id=round_id,
                details={"error": str(exc)},
            )
            logger.exception("Round %s failed: %s", round_id, exc)
