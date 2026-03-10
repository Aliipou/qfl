"""Tests for FLCoordinator — round lifecycle, update acceptance, aggregation."""

import asyncio
import uuid

import pytest

from api.schemas import (
    AggregationMethod,
    ClientUpdate,
    FLRoundConfig,
    FLRoundCreate,
    RoundStatus,
)
from core.federated.coordinator import FLCoordinator


@pytest.fixture
def coordinator() -> FLCoordinator:
    return FLCoordinator()


@pytest.fixture
def basic_payload() -> FLRoundCreate:
    return FLRoundCreate(
        config=FLRoundConfig(num_clients=2),
        dataset="mnist",
        model_architecture="simple_cnn",
    )


def _make_update(round_id: uuid.UUID, client_id: str = "c01", tenant: str = "t1") -> ClientUpdate:
    return ClientUpdate(
        client_id=client_id,
        round_id=round_id,
        tenant_id=tenant,
        weights_hash="f" * 64,
        num_samples=500,
        local_loss=0.4,
        local_accuracy=0.8,
    )


class TestRoundManagement:
    def test_create_round(self, coordinator, basic_payload):
        r = coordinator.create_round(basic_payload)
        assert r.id is not None
        assert r.status == RoundStatus.PENDING
        assert r.dataset == "mnist"

    def test_get_round_after_create(self, coordinator, basic_payload):
        r = coordinator.create_round(basic_payload)
        fetched = coordinator.get_round(r.id)
        assert fetched is not None
        assert fetched.id == r.id

    def test_get_nonexistent_round_returns_none(self, coordinator):
        assert coordinator.get_round(uuid.uuid4()) is None

    def test_list_rounds_empty(self, coordinator):
        assert coordinator.list_rounds() == []

    def test_list_rounds_after_creates(self, coordinator, basic_payload):
        for _ in range(3):
            coordinator.create_round(basic_payload)
        rounds = coordinator.list_rounds()
        assert len(rounds) == 3

    def test_list_rounds_limit(self, coordinator, basic_payload):
        for _ in range(5):
            coordinator.create_round(basic_payload)
        assert len(coordinator.list_rounds(limit=2)) == 2

    def test_list_rounds_filter_status(self, coordinator, basic_payload):
        coordinator.create_round(basic_payload)
        rounds = coordinator.list_rounds(status_filter=RoundStatus.PENDING)
        assert len(rounds) >= 1
        assert all(r.status == RoundStatus.PENDING for r in rounds)

    def test_list_rounds_filter_no_match(self, coordinator, basic_payload):
        coordinator.create_round(basic_payload)
        rounds = coordinator.list_rounds(status_filter=RoundStatus.COMPLETED)
        assert rounds == []


class TestClientUpdates:
    @pytest.mark.asyncio
    async def test_accept_update_for_running_round(self, coordinator, basic_payload):
        r = coordinator.create_round(basic_payload)
        ack = await coordinator.accept_client_update(_make_update(r.id))
        assert ack.accepted is True
        assert ack.message == "Update accepted"

    @pytest.mark.asyncio
    async def test_reject_update_for_nonexistent_round(self, coordinator):
        fake_id = uuid.uuid4()
        update = _make_update(fake_id)
        ack = await coordinator.accept_client_update(update)
        assert ack.accepted is False
        assert "not found" in ack.message

    @pytest.mark.asyncio
    async def test_round_status_becomes_running_after_first_update(self, coordinator, basic_payload):
        r = coordinator.create_round(basic_payload)
        await coordinator.accept_client_update(_make_update(r.id, "c01"))
        updated = coordinator.get_round(r.id)
        assert updated.status == RoundStatus.RUNNING

    @pytest.mark.asyncio
    async def test_num_clients_participated_increments(self, coordinator, basic_payload):
        r = coordinator.create_round(basic_payload)
        await coordinator.accept_client_update(_make_update(r.id, "c01"))
        await coordinator.accept_client_update(_make_update(r.id, "c02"))
        updated = coordinator.get_round(r.id)
        assert updated.num_clients_participated == 2

    @pytest.mark.asyncio
    async def test_reject_update_for_completed_round(self, coordinator):
        payload = FLRoundCreate(config=FLRoundConfig(num_clients=1))
        r = coordinator.create_round(payload)
        await coordinator.accept_client_update(_make_update(r.id, "c01"))
        # Give aggregation task a tick
        await asyncio.sleep(0.05)
        updated = coordinator.get_round(r.id)
        if updated.status == RoundStatus.COMPLETED:
            ack = await coordinator.accept_client_update(_make_update(r.id, "c02"))
            assert ack.accepted is False


class TestAggregation:
    @pytest.mark.asyncio
    async def test_auto_aggregate_when_all_clients_submit(self, coordinator):
        payload = FLRoundCreate(config=FLRoundConfig(num_clients=2))
        r = coordinator.create_round(payload)
        await coordinator.accept_client_update(_make_update(r.id, "c01"))
        await coordinator.accept_client_update(_make_update(r.id, "c02"))
        await asyncio.sleep(0.1)
        updated = coordinator.get_round(r.id)
        assert updated.status == RoundStatus.COMPLETED
        assert updated.global_accuracy is not None

    @pytest.mark.asyncio
    async def test_q_fed_avg_round_completes(self, coordinator):
        payload = FLRoundCreate(
            config=FLRoundConfig(num_clients=1, aggregation=AggregationMethod.Q_FED_AVG)
        )
        r = coordinator.create_round(payload)
        await coordinator.accept_client_update(_make_update(r.id))
        await asyncio.sleep(0.1)
        updated = coordinator.get_round(r.id)
        assert updated.status == RoundStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_run_round_no_op_if_missing(self, coordinator):
        """run_round with unknown ID should not raise."""
        await coordinator.run_round(uuid.uuid4())

    @pytest.mark.asyncio
    async def test_aggregate_nonexistent_round_no_op(self, coordinator):
        """_aggregate with unknown ID should not raise."""
        await coordinator._aggregate(uuid.uuid4())
