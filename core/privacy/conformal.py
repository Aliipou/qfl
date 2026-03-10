"""Conformal Prediction bounds for uncertainty quantification on aggregated model."""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class ConformalInterval:
    lower: float
    upper: float
    coverage: float
    alpha: float

    @property
    def width(self) -> float:
        return self.upper - self.lower

    def contains(self, value: float) -> bool:
        return self.lower <= value <= self.upper


def compute_nonconformity_scores(
    predictions: np.ndarray,
    labels: np.ndarray,
) -> np.ndarray:
    """
    Compute nonconformity scores for classification.

    Score = 1 - predicted probability of true class.
    """
    if predictions.ndim == 1:
        # Binary case
        scores = np.abs(predictions - labels.astype(float))
    else:
        # Multi-class: 1 - softmax_prob_of_true_class
        n = len(labels)
        true_probs = predictions[np.arange(n), labels.astype(int)]
        scores = 1.0 - true_probs

    return scores


def conformal_prediction_interval(
    calibration_scores: np.ndarray,
    alpha: float = 0.1,
) -> ConformalInterval:
    """
    Compute split conformal prediction interval.

    Args:
        calibration_scores: Nonconformity scores from calibration set.
        alpha: Miscoverage level. 1 - alpha = target coverage.

    Returns:
        ConformalInterval with guaranteed (1 - alpha) marginal coverage.
    """
    if not 0 < alpha < 1:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    if len(calibration_scores) == 0:
        raise ValueError("calibration_scores must not be empty")

    n = len(calibration_scores)
    # Adjusted quantile for finite-sample validity
    level = math.ceil((n + 1) * (1 - alpha)) / n
    level = min(level, 1.0)

    threshold = float(np.quantile(calibration_scores, level))
    coverage = 1.0 - alpha

    logger.debug(
        "Conformal interval: threshold=%.4f, coverage=%.2f, n=%d",
        threshold,
        coverage,
        n,
    )

    return ConformalInterval(
        lower=0.0,
        upper=threshold,
        coverage=coverage,
        alpha=alpha,
    )


def accuracy_prediction_set(
    global_accuracy: float,
    calibration_scores: np.ndarray,
    alpha: float = 0.1,
) -> ConformalInterval:
    """
    Wrap global model accuracy in a conformal prediction interval.

    Provides statistically valid uncertainty bounds on the reported accuracy.
    """
    interval = conformal_prediction_interval(calibration_scores, alpha)
    uncertainty = interval.width / 2
    return ConformalInterval(
        lower=max(0.0, global_accuracy - uncertainty),
        upper=min(1.0, global_accuracy + uncertainty),
        coverage=interval.coverage,
        alpha=alpha,
    )


import math  # noqa: E402 — placed after functions that reference it
