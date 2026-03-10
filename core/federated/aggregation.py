"""Classical FedAvg and QFedAvg aggregation algorithms."""

from __future__ import annotations

import logging
from typing import Sequence

import numpy as np

logger = logging.getLogger(__name__)


def fed_avg(
    weights: Sequence[list[np.ndarray]],
    num_samples: Sequence[int],
) -> list[np.ndarray]:
    """
    Classical Federated Averaging (McMahan et al., 2017).

    Computes weighted average of client model weights,
    weighted by number of local training samples.
    """
    total_samples = sum(num_samples)
    if total_samples == 0:
        raise ValueError("Total samples must be > 0")

    aggregated = [np.zeros_like(layer) for layer in weights[0]]

    for client_weights, n in zip(weights, num_samples):
        scale = n / total_samples
        for i, layer in enumerate(client_weights):
            aggregated[i] += scale * layer

    logger.info("FedAvg aggregated %d clients (%d total samples)", len(weights), total_samples)
    return aggregated


def q_fed_avg(
    weights: Sequence[list[np.ndarray]],
    num_samples: Sequence[int],
    q: float = 2.0,
) -> list[np.ndarray]:
    """
    q-FedAvg: fairness-aware aggregation (Li et al., 2020).

    Assigns higher weight to clients with larger loss (worse performance)
    to promote model fairness across heterogeneous data distributions.

    Args:
        weights: Per-client model weight arrays.
        num_samples: Number of local training samples per client.
        q: Fairness parameter. q=0 → FedAvg, higher q → more fairness.
    """
    # Placeholder: true QFedAvg needs loss values per client.
    # Phase 3 will replace this with full loss-weighted implementation.
    logger.info("q-FedAvg called with q=%.2f (Phase 1 stub → delegating to FedAvg)", q)
    return fed_avg(weights, num_samples)
