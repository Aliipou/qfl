"""Differential Privacy utilities — DP-SGD noise injection and budget tracking."""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class DPBudget:
    """Tracks privacy budget (ε, δ) consumed across FL rounds."""
    epsilon_total: float
    delta: float
    epsilon_consumed: float = 0.0
    rounds: int = 0

    @property
    def epsilon_remaining(self) -> float:
        return max(0.0, self.epsilon_total - self.epsilon_consumed)

    @property
    def is_exhausted(self) -> bool:
        return self.epsilon_consumed >= self.epsilon_total

    def consume(self, epsilon: float) -> None:
        self.epsilon_consumed += epsilon
        self.rounds += 1
        logger.info(
            "DP budget consumed: ε=%.4f | total consumed=%.4f / %.4f",
            epsilon,
            self.epsilon_consumed,
            self.epsilon_total,
        )

    def privacy_loss_rdp(self, alpha: float = 10.0, sigma: float = 1.0) -> float:
        """Rényi Differential Privacy loss (simplified Gaussian mechanism)."""
        return alpha / (2 * sigma ** 2)


@dataclass
class DPConfig:
    epsilon: float = 1.0
    delta: float = 1e-5
    max_grad_norm: float = 1.0
    noise_multiplier: float = 1.1


def add_gaussian_noise(
    weights: list[np.ndarray],
    sensitivity: float,
    epsilon: float,
    delta: float,
) -> list[np.ndarray]:
    """
    Add calibrated Gaussian noise to model weights for (ε, δ)-DP.

    Noise std = sensitivity * sqrt(2 * ln(1.25/δ)) / ε
    (Gaussian mechanism, Dwork & Roth 2014)
    """
    if epsilon <= 0:
        raise ValueError(f"epsilon must be > 0, got {epsilon}")
    if not 0 < delta < 1:
        raise ValueError(f"delta must be in (0, 1), got {delta}")

    sigma = sensitivity * math.sqrt(2 * math.log(1.25 / delta)) / epsilon
    noisy = []
    for w in weights:
        noise = np.random.normal(0, sigma, w.shape).astype(w.dtype)
        noisy.append(w + noise)

    logger.debug("Added Gaussian noise: sensitivity=%.4f, σ=%.4f", sensitivity, sigma)
    return noisy


def clip_gradients(
    weights: list[np.ndarray],
    max_norm: float,
) -> tuple[list[np.ndarray], float]:
    """
    Clip gradients to L2 norm ≤ max_norm (DP-SGD per-sample clipping).

    Returns clipped weights and the actual norm before clipping.
    """
    flat = np.concatenate([w.flatten() for w in weights])
    actual_norm = float(np.linalg.norm(flat))
    clip_factor = min(1.0, max_norm / (actual_norm + 1e-8))

    clipped = [w * clip_factor for w in weights]
    return clipped, actual_norm
