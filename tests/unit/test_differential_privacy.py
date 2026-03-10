"""Unit tests for differential privacy utilities."""

import numpy as np
import pytest

from core.privacy.differential import (
    DPBudget,
    DPConfig,
    add_gaussian_noise,
    clip_gradients,
)


class TestDPBudget:
    def test_initial_state(self):
        b = DPBudget(epsilon_total=10.0, delta=1e-5)
        assert b.epsilon_consumed == 0.0
        assert b.epsilon_remaining == 10.0
        assert b.is_exhausted is False
        assert b.rounds == 0

    def test_consume_reduces_remaining(self):
        b = DPBudget(epsilon_total=5.0, delta=1e-5)
        b.consume(1.5)
        assert abs(b.epsilon_remaining - 3.5) < 1e-9
        assert b.rounds == 1

    def test_exhausted_after_full_consumption(self):
        b = DPBudget(epsilon_total=2.0, delta=1e-5)
        b.consume(2.0)
        assert b.is_exhausted is True

    def test_remaining_clamps_to_zero(self):
        b = DPBudget(epsilon_total=1.0, delta=1e-5)
        b.consume(5.0)  # Over-consume
        assert b.epsilon_remaining == 0.0

    def test_rounds_increment(self):
        b = DPBudget(epsilon_total=100.0, delta=1e-5)
        for _ in range(5):
            b.consume(1.0)
        assert b.rounds == 5

    def test_privacy_loss_rdp(self):
        b = DPBudget(epsilon_total=10.0, delta=1e-5)
        loss = b.privacy_loss_rdp(alpha=10.0, sigma=1.0)
        assert loss == pytest.approx(5.0)

    def test_rdp_custom_params(self):
        b = DPBudget(epsilon_total=10.0, delta=1e-5)
        loss = b.privacy_loss_rdp(alpha=5.0, sigma=2.0)
        assert loss == pytest.approx(5.0 / 8.0)


class TestDPConfig:
    def test_defaults(self):
        c = DPConfig()
        assert c.epsilon == 1.0
        assert c.delta == 1e-5
        assert c.max_grad_norm == 1.0
        assert c.noise_multiplier == 1.1

    def test_custom(self):
        c = DPConfig(epsilon=0.5, max_grad_norm=5.0)
        assert c.epsilon == 0.5


class TestAddGaussianNoise:
    def test_output_shape_preserved(self):
        weights = [np.ones((5, 5)), np.zeros(5)]
        noisy = add_gaussian_noise(weights, sensitivity=1.0, epsilon=1.0, delta=1e-5)
        assert noisy[0].shape == (5, 5)
        assert noisy[1].shape == (5,)

    def test_noise_changes_values(self):
        weights = [np.zeros(100)]
        noisy = add_gaussian_noise(weights, sensitivity=1.0, epsilon=1.0, delta=1e-5)
        assert not np.allclose(noisy[0], 0.0)

    def test_smaller_epsilon_more_noise(self):
        rng = np.random.default_rng(0)
        base = [rng.standard_normal(1000)]

        np.random.seed(42)
        noisy_tight = add_gaussian_noise(base, 1.0, epsilon=0.1, delta=1e-5)
        np.random.seed(42)
        noisy_loose = add_gaussian_noise(base, 1.0, epsilon=10.0, delta=1e-5)

        tight_std = np.std(noisy_tight[0] - base[0])
        loose_std = np.std(noisy_loose[0] - base[0])
        assert tight_std > loose_std

    def test_invalid_epsilon_raises(self):
        with pytest.raises(ValueError, match="epsilon must be > 0"):
            add_gaussian_noise([np.zeros(5)], 1.0, epsilon=0.0, delta=1e-5)

    def test_invalid_delta_zero_raises(self):
        with pytest.raises(ValueError, match="delta must be in"):
            add_gaussian_noise([np.zeros(5)], 1.0, epsilon=1.0, delta=0.0)

    def test_invalid_delta_one_raises(self):
        with pytest.raises(ValueError, match="delta must be in"):
            add_gaussian_noise([np.zeros(5)], 1.0, epsilon=1.0, delta=1.0)


class TestClipGradients:
    def test_clipping_reduces_large_norm(self):
        weights = [np.ones(1000) * 100.0]
        clipped, norm = clip_gradients(weights, max_norm=1.0)
        flat = np.concatenate([w.flatten() for w in clipped])
        assert np.linalg.norm(flat) <= 1.0 + 1e-6

    def test_small_weights_not_clipped(self):
        weights = [np.ones(10) * 0.01]
        clipped, norm = clip_gradients(weights, max_norm=100.0)
        np.testing.assert_allclose(clipped[0], weights[0], rtol=1e-5)

    def test_returns_actual_norm(self):
        weights = [np.array([3.0, 4.0])]
        _, norm = clip_gradients(weights, max_norm=10.0)
        assert abs(norm - 5.0) < 1e-5

    def test_multi_layer(self):
        weights = [np.ones((10, 10)), np.ones(10)]
        clipped, _ = clip_gradients(weights, max_norm=1.0)
        assert len(clipped) == 2
