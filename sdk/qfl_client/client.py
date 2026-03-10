"""QFL Python SDK — qfl.train(model, data)."""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)


class QFLClient:
    """
    Async-capable QFL Platform client SDK.

    Usage:
        client = QFLClient("https://qfl.example.com")
        round = client.start_round(num_clients=3, dataset="mnist")
        client.submit_update(round.id, weights, num_samples=1000, accuracy=0.92)
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        tenant_id: str = "default",
        timeout: float = 30.0,
        api_key: str | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.tenant_id = tenant_id
        self._timeout = timeout
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self._client = httpx.Client(
            base_url=self.base_url,
            headers=headers,
            timeout=self._timeout,
        )

    # ------------------------------------------------------------------
    # Health
    # ------------------------------------------------------------------

    def health(self) -> dict[str, Any]:
        resp = self._client.get("/health")
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Training
    # ------------------------------------------------------------------

    def start_round(
        self,
        num_clients: int = 3,
        dataset: str = "mnist",
        model_architecture: str = "simple_cnn",
        aggregation: str = "fed_avg",
        dp_epsilon: float = 1.0,
        use_quantum: bool = False,
    ) -> dict[str, Any]:
        payload = {
            "config": {
                "num_clients": num_clients,
                "aggregation": aggregation,
                "dp_epsilon": dp_epsilon,
                "use_quantum": use_quantum,
            },
            "dataset": dataset,
            "model_architecture": model_architecture,
        }
        resp = self._client.post("/train", json=payload)
        resp.raise_for_status()
        return resp.json()

    def submit_update(
        self,
        round_id: str | UUID,
        weights_hash: str,
        num_samples: int,
        local_loss: float,
        local_accuracy: float,
        client_id: str = "sdk_client",
        dp_noise_applied: bool = False,
        qkd_key_id: str | None = None,
    ) -> dict[str, Any]:
        rid = str(round_id)
        payload = {
            "client_id": client_id,
            "round_id": rid,
            "tenant_id": self.tenant_id,
            "weights_hash": weights_hash,
            "num_samples": num_samples,
            "local_loss": local_loss,
            "local_accuracy": local_accuracy,
            "dp_noise_applied": dp_noise_applied,
            "qkd_key_id": qkd_key_id,
        }
        resp = self._client.post(f"/train/{rid}/update", json=payload)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_round(self, round_id: str | UUID) -> dict[str, Any]:
        resp = self._client.get(f"/status/{round_id}")
        resp.raise_for_status()
        return resp.json()

    def list_rounds(self, limit: int = 20) -> list[dict[str, Any]]:
        resp = self._client.get("/status", params={"limit": limit})
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Audit
    # ------------------------------------------------------------------

    def audit_report(self, tenant_id: str | None = None) -> dict[str, Any]:
        tid = tenant_id or self.tenant_id
        resp = self._client.get(f"/audit/report/{tid}")
        resp.raise_for_status()
        return resp.json()

    def audit_events(
        self,
        round_id: str | None = None,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        params: dict[str, Any] = {"limit": limit, "tenant_id": self.tenant_id}
        if round_id:
            params["round_id"] = round_id
        resp = self._client.get("/audit/events", params=params)
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Context manager
    # ------------------------------------------------------------------

    def __enter__(self) -> QFLClient:
        return self

    def __exit__(self, *_: Any) -> None:
        self._client.close()

    def close(self) -> None:
        self._client.close()
