"""Unit tests for FedAvg and QFedAvg aggregation."""

import numpy as np
import pytest

from core.federated.aggregation import fed_avg, q_fed_avg


def _make_weights(n_clients: int, shape: tuple = (4, 4)) -> list[list[np.ndarray]]:
    rng = np.random.default_rng(seed=42)
    return [[rng.standard_normal(shape).astype(np.float32)] for _ in range(n_clients)]


class TestFedAvg:
    def test_uniform_weights_equal_mean(self):
        w = [
            [np.array([1.0, 2.0])],
            [np.array([3.0, 4.0])],
        ]
        result = fed_avg(w, [1, 1])
        np.testing.assert_allclose(result[0], [2.0, 3.0])

    def test_weighted_by_num_samples(self):
        w = [
            [np.array([0.0])],
            [np.array([4.0])],
        ]
        # 1 sample vs 3 samples → result = 3.0
        result = fed_avg(w, [1, 3])
        np.testing.assert_allclose(result[0], [3.0])

    def test_single_client_returns_same_weights(self):
        w = [[np.array([5.0, -1.0, 3.0])]]
        result = fed_avg(w, [100])
        np.testing.assert_array_equal(result[0], w[0][0])

    def test_multi_layer_model(self):
        w = [
            [np.ones((3, 3)), np.zeros(3)],
            [np.zeros((3, 3)), np.ones(3)],
        ]
        result = fed_avg(w, [1, 1])
        np.testing.assert_allclose(result[0], 0.5 * np.ones((3, 3)))
        np.testing.assert_allclose(result[1], 0.5 * np.ones(3))

    def test_zero_samples_raises(self):
        w = _make_weights(2)
        with pytest.raises(ValueError, match="Total samples must be > 0"):
            fed_avg(w, [0, 0])

    def test_output_shape_preserved(self):
        w = _make_weights(3, shape=(10, 20))
        result = fed_avg(w, [100, 200, 300])
        assert result[0].shape == (10, 20)

    def test_ten_clients(self):
        w = _make_weights(10)
        n = [100] * 10
        result = fed_avg(w, n)
        assert result[0].shape == (4, 4)


class TestQFedAvg:
    def test_q_fed_avg_returns_correct_shape(self):
        w = _make_weights(3)
        result = q_fed_avg(w, [100, 200, 300])
        assert result[0].shape == (4, 4)

    def test_q_fed_avg_delegates_to_fed_avg_phase1(self):
        """Phase 1: QFedAvg is a stub that calls FedAvg."""
        w = [
            [np.array([2.0])],
            [np.array([8.0])],
        ]
        fed = fed_avg(w, [1, 1])
        qfed = q_fed_avg(w, [1, 1], q=2.0)
        np.testing.assert_array_equal(fed[0], qfed[0])

    def test_q_fed_avg_default_q(self):
        w = _make_weights(2)
        result = q_fed_avg(w, [50, 50])
        assert result is not None
