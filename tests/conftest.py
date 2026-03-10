"""Shared pytest fixtures for QFL Platform tests."""

import asyncio
import uuid
from datetime import datetime

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from httpx import AsyncClient

from api.main import app
from api.schemas import (
    AggregationMethod,
    AuditEvent,
    ClientUpdate,
    FLRoundConfig,
    FLRoundCreate,
    RiskLevel,
)


# ---------------------------------------------------------------------------
# App clients
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def sync_client() -> TestClient:
    return TestClient(app)


@pytest_asyncio.fixture
async def async_client():
    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client


# ---------------------------------------------------------------------------
# FL round fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_round_config() -> FLRoundConfig:
    return FLRoundConfig(
        num_clients=3,
        local_epochs=5,
        learning_rate=0.01,
        aggregation=AggregationMethod.FED_AVG,
        dp_epsilon=1.0,
        dp_delta=1e-5,
        use_quantum=False,
    )


@pytest.fixture
def quantum_round_config() -> FLRoundConfig:
    return FLRoundConfig(
        num_clients=2,
        local_epochs=2,
        aggregation=AggregationMethod.Q_FED_AVG,
        use_quantum=True,
    )


@pytest.fixture
def round_create_payload(default_round_config) -> FLRoundCreate:
    return FLRoundCreate(
        config=default_round_config,
        dataset="mnist",
        model_architecture="simple_cnn",
    )


@pytest.fixture
def client_update_factory():
    def _make(round_id: uuid.UUID, client_num: int = 1, tenant: str = "tenant_a") -> ClientUpdate:
        return ClientUpdate(
            client_id=f"client_{client_num:02d}",
            round_id=round_id,
            tenant_id=tenant,
            weights_hash="abc" * 21 + "d",  # 64 chars
            num_samples=500 + client_num * 100,
            local_loss=0.5 - client_num * 0.05,
            local_accuracy=0.7 + client_num * 0.05,
            dp_noise_applied=True,
            qkd_key_id=f"key_{client_num:04x}",
        )
    return _make
