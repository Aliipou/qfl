"""
Privacy Budget Analysis
=======================
Produces the privacy-utility tradeoff curve used in Figure 2 of the paper.

Sweeps epsilon from 0.1 to ∞ (no DP) and records:
  - Peak global accuracy
  - Accuracy drop vs. no-DP baseline
  - DP budget consumed per round
  - Effective privacy guarantee (RDP accounting)

Output:
  benchmarks/results/privacy_sweep.csv
  benchmarks/results/rdp_accounting.csv
"""

from __future__ import annotations

import csv
import logging
import math
from pathlib import Path

import numpy as np

from benchmarks.fl_benchmark import (
    RESULTS_DIR,
    _make_numpy_mnist,
    _make_model_weights,
    _local_train,
    _accuracy,
    dirichlet_split,
)
from core.federated.aggregation import fed_avg
from core.privacy.differential import DPBudget

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(message)s", datefmt="%H:%M:%S")


def rdp_to_dp(rdp_epsilon: float, alpha: float, delta: float) -> float:
    """Convert Rényi DP (α, ε_RDP) to (ε, δ)-DP via standard conversion."""
    return rdp_epsilon + math.log(1 / delta) / (alpha - 1)


def gaussian_rdp(sigma: float, alpha: float) -> float:
    """RDP epsilon for Gaussian mechanism with noise multiplier sigma."""
    return alpha / (2 * sigma ** 2)


def run_privacy_sweep(
    epsilons: list[float | None],
    n_rounds: int = 15,
    n_clients: int = 3,
    n_samples: int = 4000,
    delta: float = 1e-5,
) -> list[dict]:
    """Sweep over epsilon values and record accuracy vs. privacy."""
    X, y = _make_numpy_mnist(n_samples)
    splits = dirichlet_split(y, n_clients, alpha=0.5)
    test_idx = np.random.default_rng(99).choice(len(X), size=800, replace=False)
    X_test, y_test = X[test_idx], y[test_idx]

    rows = []

    for eps in epsilons:
        log.info("Privacy sweep: ε=%s", eps)
        global_weights = _make_model_weights()

        for rnd in range(n_rounds):
            client_weights, client_samples = [], []
            for c in range(n_clients):
                idx = splits[c]
                w, _, _, _ = _local_train(
                    global_weights, X[idx], y[idx],
                    epochs=5, lr=0.01,
                    dp_epsilon=eps, dp_delta=delta,
                )
                client_weights.append(w)
                client_samples.append(len(idx))
            global_weights = fed_avg(client_weights, client_samples)

        peak_acc = _accuracy(global_weights, X_test, y_test)

        # RDP accounting (Gaussian mechanism, noise_multiplier=1.1)
        sigma = 1.1
        alpha = 10.0
        rdp_eps = gaussian_rdp(sigma, alpha) * n_rounds
        dp_eps_formal = rdp_to_dp(rdp_eps, alpha, delta) if eps is not None else None

        rows.append({
            "epsilon_config": str(eps) if eps else "None (no DP)",
            "peak_accuracy": round(peak_acc, 4),
            "dp_budget_consumed": round(eps * n_rounds, 3) if eps else 0.0,
            "rdp_epsilon": round(rdp_eps, 4),
            "formal_dp_epsilon": round(dp_eps_formal, 4) if dp_eps_formal else "N/A",
            "delta": delta,
            "rounds": n_rounds,
        })

        log.info(
            "  ε=%-8s → acc=%.4f | RDP ε=%.4f",
            str(eps) if eps else "∞", peak_acc, rdp_eps,
        )

    return rows


def export_privacy_sweep(rows: list[dict]) -> None:
    path = RESULTS_DIR / "privacy_sweep.csv"
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    log.info("Saved: %s", path)

    # Also write RDP accounting table
    rdp_path = RESULTS_DIR / "rdp_accounting.csv"
    with open(rdp_path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["epsilon_config", "rdp_epsilon_per_round",
                         "rdp_epsilon_total", "formal_dp_epsilon"])
        sigma = 1.1
        for row in rows:
            eps_cfg = row["epsilon_config"]
            rdp_per = gaussian_rdp(sigma, alpha=10.0)
            rdp_total = row["rdp_epsilon"]
            formal = row["formal_dp_epsilon"]
            writer.writerow([eps_cfg, round(rdp_per, 6), rdp_total, formal])
    log.info("Saved: %s", rdp_path)


if __name__ == "__main__":
    epsilons: list[float | None] = [None, 10.0, 5.0, 2.0, 1.0, 0.5, 0.1]
    rows = run_privacy_sweep(epsilons, n_rounds=15, n_samples=4000)
    export_privacy_sweep(rows)

    print("\n Privacy-Utility Tradeoff")
    print(f"{'eps Config':<20} {'Peak Acc':>10} {'Budget Used':>13} {'Formal eps':>10}")
    print("-" * 57)
    for r in rows:
        print(
            f"{r['epsilon_config']:<20} {r['peak_accuracy'] * 100:>9.2f}%"
            f" {r['dp_budget_consumed']:>13.1f} {str(r['formal_dp_epsilon']):>10}"
        )
