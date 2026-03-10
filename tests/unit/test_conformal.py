"""Unit tests for conformal prediction bounds."""

import numpy as np
import pytest

from core.privacy.conformal import (
    ConformalInterval,
    accuracy_prediction_set,
    compute_nonconformity_scores,
    conformal_prediction_interval,
)


class TestConformalInterval:
    def test_width(self):
        ci = ConformalInterval(lower=0.1, upper=0.9, coverage=0.9, alpha=0.1)
        assert ci.width == pytest.approx(0.8)

    def test_contains_true(self):
        ci = ConformalInterval(lower=0.2, upper=0.8, coverage=0.9, alpha=0.1)
        assert ci.contains(0.5) is True

    def test_contains_false(self):
        ci = ConformalInterval(lower=0.2, upper=0.8, coverage=0.9, alpha=0.1)
        assert ci.contains(0.9) is False

    def test_contains_boundary(self):
        ci = ConformalInterval(lower=0.0, upper=1.0, coverage=0.9, alpha=0.1)
        assert ci.contains(0.0) is True
        assert ci.contains(1.0) is True


class TestNonconformityScores:
    def test_binary_case(self):
        preds = np.array([0.8, 0.3, 0.7])
        labels = np.array([1, 0, 0])
        scores = compute_nonconformity_scores(preds, labels)
        expected = np.abs(preds - labels)
        np.testing.assert_allclose(scores, expected)

    def test_multiclass_case(self):
        preds = np.array([
            [0.1, 0.8, 0.1],
            [0.7, 0.2, 0.1],
        ])
        labels = np.array([1, 0])
        scores = compute_nonconformity_scores(preds, labels)
        # Class 1 prob=0.8 → score=0.2; Class 0 prob=0.7 → score=0.3
        np.testing.assert_allclose(scores, [0.2, 0.3], atol=1e-6)


class TestConformalPredictionInterval:
    def test_valid_interval(self):
        scores = np.random.default_rng(42).uniform(0, 1, 100)
        ci = conformal_prediction_interval(scores, alpha=0.1)
        assert 0 <= ci.lower <= ci.upper <= 1
        assert ci.coverage == pytest.approx(0.9)
        assert ci.alpha == 0.1

    def test_lower_alpha_wider_interval(self):
        scores = np.linspace(0, 1, 200)
        ci_tight = conformal_prediction_interval(scores, alpha=0.3)
        ci_wide = conformal_prediction_interval(scores, alpha=0.05)
        assert ci_wide.upper >= ci_tight.upper

    def test_invalid_alpha_zero(self):
        with pytest.raises(ValueError, match="alpha must be"):
            conformal_prediction_interval(np.ones(10), alpha=0.0)

    def test_invalid_alpha_one(self):
        with pytest.raises(ValueError, match="alpha must be"):
            conformal_prediction_interval(np.ones(10), alpha=1.0)

    def test_empty_scores_raises(self):
        with pytest.raises(ValueError, match="must not be empty"):
            conformal_prediction_interval(np.array([]), alpha=0.1)


class TestAccuracyPredictionSet:
    def test_returns_interval(self):
        scores = np.random.default_rng(0).uniform(0, 0.5, 100)
        ci = accuracy_prediction_set(0.9, scores, alpha=0.1)
        assert isinstance(ci, ConformalInterval)
        assert 0.0 <= ci.lower <= ci.upper <= 1.0

    def test_lower_clamps_to_zero(self):
        # Wide scores → lower might want to go negative
        scores = np.ones(50) * 0.9
        ci = accuracy_prediction_set(0.05, scores, alpha=0.1)
        assert ci.lower >= 0.0

    def test_upper_clamps_to_one(self):
        scores = np.zeros(50)  # Zero nonconformity
        ci = accuracy_prediction_set(0.99, scores, alpha=0.1)
        assert ci.upper <= 1.0
