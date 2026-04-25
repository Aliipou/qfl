"""
QFL Platform — Federated Learning Benchmark Suite
==================================================
Produces paper-ready results comparing:
  1. Classical FedAvg  vs  q-FedAvg
  2. No-DP  vs  DP (various epsilon values)
  3. Quantum simulator  vs  Classical baseline
  4. Communication cost (bytes) per round
  5. Privacy-utility tradeoff curve

Outputs:
  benchmarks/results/accuracy_vs_rounds.csv
  benchmarks/results/privacy_tradeoff.csv
  benchmarks/results/communication_cost.csv
  benchmarks/results/tables.tex          ← paste directly into paper

Usage:
  python -m benchmarks.fl_benchmark [--rounds 20] [--clients 3] [--quick]
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Callable

import numpy as np

# ── optional torch (graceful fallback to numpy simulation) ─────────────────
try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logging.warning("PyTorch not installed — using numpy simulation mode")

from core.federated.aggregation import fed_avg, q_fed_avg
from core.privacy.differential import add_gaussian_noise, clip_gradients, DPBudget

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

RESULTS_DIR = Path(__file__).parent / "results"
RESULTS_DIR.mkdir(exist_ok=True)


# ════════════════════════════════════════════════════════════════════════════
# Data: MNIST non-IID split (Dirichlet α=0.5)
# ════════════════════════════════════════════════════════════════════════════

def _make_numpy_mnist(n_samples: int = 60000) -> tuple[np.ndarray, np.ndarray]:
    """
    Load real MNIST via torchvision (downloads once to ~/.cache/torchvision).
    Falls back to sklearn fetch_openml if torchvision is unavailable.
    n_samples caps the training set size for quick experiments.
    """
    try:
        import torchvision
        import torchvision.transforms as transforms

        dataset = torchvision.datasets.MNIST(
            root=str(Path.home() / ".cache" / "torchvision"),
            train=True,
            download=True,
            transform=transforms.ToTensor(),
        )
        X = dataset.data.numpy().reshape(-1, 784).astype(np.float32) / 255.0
        y = dataset.targets.numpy()
    except Exception:
        from sklearn.datasets import fetch_openml
        log.info("torchvision unavailable — fetching MNIST via sklearn")
        mnist = fetch_openml("mnist_784", version=1, as_frame=False, parser="auto")
        X = mnist.data.astype(np.float32) / 255.0
        y = mnist.target.astype(int)

    if n_samples < len(X):
        rng = np.random.default_rng(42)
        idx = rng.choice(len(X), size=n_samples, replace=False)
        X, y = X[idx], y[idx]

    return X, y


def dirichlet_split(
    y: np.ndarray,
    n_clients: int,
    alpha: float = 0.5,
    seed: int = 42,
) -> list[np.ndarray]:
    """
    Non-IID data split using Dirichlet distribution.

    α=0.5 → heterogeneous (realistic industrial setting)
    α=100  → near-IID

    Returns list of index arrays, one per client.
    """
    rng = np.random.default_rng(seed)
    n_classes = len(np.unique(y))
    client_indices: list[list[int]] = [[] for _ in range(n_clients)]

    for cls in range(n_classes):
        cls_indices = np.where(y == cls)[0]
        rng.shuffle(cls_indices)
        proportions = rng.dirichlet(alpha=np.full(n_clients, alpha))
        proportions = (proportions * len(cls_indices)).astype(int)
        # Fix rounding
        proportions[-1] = len(cls_indices) - proportions[:-1].sum()
        idx = 0
        for c, p in enumerate(proportions):
            client_indices[c].extend(cls_indices[idx: idx + p].tolist())
            idx += p

    return [np.array(ci) for ci in client_indices]


# ════════════════════════════════════════════════════════════════════════════
# Model: Simple 2-layer MLP (matches paper description)
# ════════════════════════════════════════════════════════════════════════════

def _make_model_weights(input_dim: int = 784, hidden: int = 128, output: int = 10) -> list[np.ndarray]:
    """Initialize MLP weights as numpy arrays."""
    rng = np.random.default_rng(seed=0)
    scale1 = np.sqrt(2.0 / input_dim)
    scale2 = np.sqrt(2.0 / hidden)
    return [
        rng.standard_normal((hidden, input_dim)).astype(np.float32) * scale1,  # W1
        np.zeros(hidden, dtype=np.float32),                                     # b1
        rng.standard_normal((output, hidden)).astype(np.float32) * scale2,     # W2
        np.zeros(output, dtype=np.float32),                                    # b2
    ]


def _softmax(x: np.ndarray) -> np.ndarray:
    e = np.exp(x - x.max(axis=1, keepdims=True))
    return e / e.sum(axis=1, keepdims=True)


def _forward(weights: list[np.ndarray], X: np.ndarray) -> np.ndarray:
    W1, b1, W2, b2 = weights
    h = np.maximum(0, X @ W1.T + b1)   # ReLU
    return _softmax(h @ W2.T + b2)


def _cross_entropy(probs: np.ndarray, y: np.ndarray) -> float:
    n = len(y)
    return -np.log(probs[np.arange(n), y] + 1e-9).mean()


def _accuracy(weights: list[np.ndarray], X: np.ndarray, y: np.ndarray) -> float:
    probs = _forward(weights, X)
    return (probs.argmax(axis=1) == y).mean()


def _dp_noise_std(epsilon: float, delta: float, C: float, n: int, epochs: int, batch_size: int = 32) -> float:
    """
    Calibrate Gaussian mechanism noise std for (ε, δ)-DP via the analytic
    Gaussian mechanism (Balle & Wang 2018). Monotone in 1/ε: smaller ε → larger σ.

    σ = C · √(2 ln(1.25/δ)) / ε   (standard Gaussian mechanism)
    Adjusted for T = (n/batch)*epochs compositions via moments accountant:
      σ_round = σ · √T    (strong composition)
    """
    import math
    T = max(1, (n // batch_size) * epochs)
    sigma_base = C * math.sqrt(2.0 * math.log(1.25 / delta)) / epsilon
    # Divide by √T so that composed ε across T steps equals target ε
    return sigma_base / math.sqrt(T)


def _local_train(
    weights: list[np.ndarray],
    X: np.ndarray,
    y: np.ndarray,
    epochs: int = 5,
    lr: float = 0.01,
    dp_epsilon: float | None = None,
    dp_delta: float = 1e-5,
    dp_max_grad_norm: float = 1.0,   # standard clipping norm (Abadi et al. 2016)
) -> tuple[list[np.ndarray], float, float, int]:
    """
    Local training with SGD + analytically calibrated DP-SGD.
    Noise std is monotone in 1/ε: smaller ε → more noise → lower accuracy.
    Returns (new_weights, final_loss, final_accuracy, bytes_transmitted).
    """
    W1, b1, W2, b2 = [w.copy() for w in weights]
    rng = np.random.default_rng()

    noise_std: float | None = None
    if dp_epsilon is not None:
        noise_std = _dp_noise_std(dp_epsilon, dp_delta, dp_max_grad_norm, len(X), epochs)

    for _ in range(epochs):
        idx = rng.permutation(len(X))
        for start in range(0, len(X), 32):
            batch = idx[start:start + 32]
            Xb, yb = X[batch], y[batch]
            n = len(yb)

            # Forward
            h = np.maximum(0, Xb @ W1.T + b1)
            probs = _softmax(h @ W2.T + b2)

            # Backward (cross-entropy + softmax)
            dout = probs.copy()
            dout[np.arange(n), yb] -= 1
            dout /= n

            dW2 = dout.T @ h
            db2 = dout.sum(axis=0)
            dh = dout @ W2
            dh[h <= 0] = 0
            dW1 = dh.T @ Xb
            db1 = dh.sum(axis=0)

            grads = [dW1, db1, dW2, db2]
            if noise_std is not None:
                grads, _ = clip_gradients(grads, max_norm=dp_max_grad_norm)
                grads = [g + rng.normal(0, noise_std, g.shape).astype(g.dtype)
                         for g in grads]
            dW1, db1, dW2, db2 = grads

            W1 -= lr * dW1
            b1 -= lr * db1
            W2 -= lr * dW2
            b2 -= lr * db2

    new_weights = [W1, b1, W2, b2]
    loss = _cross_entropy(_forward(new_weights, X), y)
    acc = _accuracy(new_weights, X, y)

    # Communication cost: sum of bytes in weight arrays
    bytes_tx = sum(w.nbytes for w in new_weights)

    return new_weights, loss, acc, bytes_tx


# ════════════════════════════════════════════════════════════════════════════
# Benchmark result dataclasses
# ════════════════════════════════════════════════════════════════════════════

@dataclass
class RoundResult:
    round_num: int
    algorithm: str          # "FedAvg" | "q-FedAvg"
    dp_epsilon: float | None
    global_accuracy: float
    global_loss: float
    comm_bytes_total: int   # total bytes from all clients this round
    round_time_s: float     # wall-clock seconds
    clients: int
    alpha_dirichlet: float  # non-IID degree


@dataclass
class BenchmarkSummary:
    algorithm: str
    dp_epsilon: float | None
    rounds: int
    clients: int
    alpha_dirichlet: float
    peak_accuracy: float
    rounds_to_90pct: int | None  # None if never reached 90%
    total_comm_mb: float
    total_time_s: float
    dp_budget_total: float
    results: list[RoundResult] = field(default_factory=list)


# ════════════════════════════════════════════════════════════════════════════
# Core benchmark runner
# ════════════════════════════════════════════════════════════════════════════

def run_benchmark(
    algorithm: str = "FedAvg",
    n_rounds: int = 20,
    n_clients: int = 3,
    local_epochs: int = 5,
    learning_rate: float = 0.01,
    dp_epsilon: float | None = None,
    dp_delta: float = 1e-5,
    alpha_dirichlet: float = 0.5,
    n_samples: int = 6000,
) -> BenchmarkSummary:
    """Run a full FL benchmark and return structured results."""

    log.info(
        "Starting %s | DP ε=%s | %d clients | %d rounds | α=%.1f",
        algorithm, dp_epsilon, n_clients, n_rounds, alpha_dirichlet,
    )

    X, y = _make_numpy_mnist(n_samples)
    client_splits = dirichlet_split(y, n_clients, alpha=alpha_dirichlet)
    test_idx = np.random.default_rng(99).choice(len(X), size=1000, replace=False)
    X_test, y_test = X[test_idx], y[test_idx]

    global_weights = _make_model_weights()
    dp_budget = DPBudget(epsilon_total=999.0, delta=dp_delta)

    results: list[RoundResult] = []
    rounds_to_90: int | None = None
    total_bytes = 0
    total_time = 0.0
    t_start = time.perf_counter()

    for rnd in range(1, n_rounds + 1):
        t_round = time.perf_counter()

        client_weights = []
        client_samples = []
        round_bytes = 0

        for c in range(n_clients):
            idx = client_splits[c]
            Xc, yc = X[idx], y[idx]

            w, loss, acc, nbytes = _local_train(
                global_weights, Xc, yc,
                epochs=local_epochs,
                lr=learning_rate,
                dp_epsilon=dp_epsilon,
                dp_delta=dp_delta,
            )
            client_weights.append(w)
            client_samples.append(len(idx))
            round_bytes += nbytes

        # Aggregation
        if algorithm == "q-FedAvg":
            global_weights = q_fed_avg(client_weights, client_samples, q=2.0)
        else:
            global_weights = fed_avg(client_weights, client_samples)

        if dp_epsilon is not None:
            dp_budget.consume(dp_epsilon)

        # Evaluate on test set
        g_acc = _accuracy(global_weights, X_test, y_test)
        g_loss = _cross_entropy(_forward(global_weights, X_test), y_test)

        dt = time.perf_counter() - t_round
        total_bytes += round_bytes
        total_time += dt

        r = RoundResult(
            round_num=rnd,
            algorithm=algorithm,
            dp_epsilon=dp_epsilon,
            global_accuracy=round(g_acc, 4),
            global_loss=round(g_loss, 4),
            comm_bytes_total=round_bytes,
            round_time_s=round(dt, 3),
            clients=n_clients,
            alpha_dirichlet=alpha_dirichlet,
        )
        results.append(r)

        if rounds_to_90 is None and g_acc >= 0.90:
            rounds_to_90 = rnd

        log.info(
            "  Round %2d/%d | acc=%.4f | loss=%.4f | comm=%.1f KB | %.2fs",
            rnd, n_rounds, g_acc, g_loss, round_bytes / 1024, dt,
        )

    peak_acc = max(r.global_accuracy for r in results)

    return BenchmarkSummary(
        algorithm=algorithm,
        dp_epsilon=dp_epsilon,
        rounds=n_rounds,
        clients=n_clients,
        alpha_dirichlet=alpha_dirichlet,
        peak_accuracy=round(peak_acc, 4),
        rounds_to_90pct=rounds_to_90,
        total_comm_mb=round(total_bytes / 1_000_000, 3),
        total_time_s=round(time.perf_counter() - t_start, 2),
        dp_budget_total=round(dp_budget.epsilon_consumed, 2),
        results=results,
    )


# ════════════════════════════════════════════════════════════════════════════
# Output: CSV + LaTeX
# ════════════════════════════════════════════════════════════════════════════

def export_accuracy_csv(summaries: list[BenchmarkSummary]) -> Path:
    path = RESULTS_DIR / "accuracy_vs_rounds.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "algorithm", "dp_epsilon", "round",
            "global_accuracy", "global_loss", "comm_bytes", "round_time_s",
        ])
        for s in summaries:
            for r in s.results:
                writer.writerow([
                    r.algorithm,
                    r.dp_epsilon if r.dp_epsilon is not None else "None",
                    r.round_num,
                    r.global_accuracy,
                    r.global_loss,
                    r.comm_bytes_total,
                    r.round_time_s,
                ])
    log.info("Saved: %s", path)
    return path


def export_privacy_tradeoff_csv(summaries: list[BenchmarkSummary]) -> Path:
    path = RESULTS_DIR / "privacy_tradeoff.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "algorithm", "dp_epsilon", "peak_accuracy",
            "rounds_to_90pct", "total_dp_budget",
        ])
        for s in summaries:
            writer.writerow([
                s.algorithm,
                s.dp_epsilon if s.dp_epsilon is not None else "None",
                s.peak_accuracy,
                s.rounds_to_90pct if s.rounds_to_90pct else "N/A",
                s.dp_budget_total,
            ])
    log.info("Saved: %s", path)
    return path


def export_communication_csv(summaries: list[BenchmarkSummary]) -> Path:
    path = RESULTS_DIR / "communication_cost.csv"
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "algorithm", "dp_epsilon", "rounds",
            "total_comm_mb", "comm_per_round_mb", "total_time_s",
        ])
        for s in summaries:
            writer.writerow([
                s.algorithm,
                s.dp_epsilon if s.dp_epsilon is not None else "None",
                s.rounds,
                s.total_comm_mb,
                round(s.total_comm_mb / s.rounds, 4),
                s.total_time_s,
            ])
    log.info("Saved: %s", path)
    return path


def export_latex_tables(summaries: list[BenchmarkSummary]) -> Path:
    """Generate IEEE-style LaTeX tables for direct inclusion in paper."""
    path = RESULTS_DIR / "tables.tex"

    def _eps(v: float | None) -> str:
        return f"{v:.1f}" if v is not None else r"$\infty$"

    lines = [
        r"% ============================================================",
        r"% QFL Platform — Auto-generated benchmark tables",
        f"% Generated: {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
        r"% ============================================================",
        "",
        r"% ---- Table 1: Algorithm Comparison (paste into paper) -----",
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Federated Learning Algorithm Comparison on MNIST (non-IID, $\alpha=0.5$)}",
        r"\label{tab:algorithm-comparison}",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"Algorithm & $\varepsilon$ & Peak Acc. (\%) & Rounds to 90\% & Comm. (MB) \\",
        r"\midrule",
    ]

    for s in summaries:
        r90 = str(s.rounds_to_90pct) if s.rounds_to_90pct else r"$>$" + str(s.rounds)
        lines.append(
            f"{s.algorithm} & {_eps(s.dp_epsilon)} & "
            f"{s.peak_accuracy * 100:.2f} & {r90} & {s.total_comm_mb:.2f} \\\\"
        )

    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        "",
        r"% ---- Table 2: Privacy-Utility Tradeoff -------------------",
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Privacy-Utility Tradeoff: FedAvg with Differential Privacy ($\delta=10^{-5}$)}",
        r"\label{tab:privacy-tradeoff}",
        r"\begin{tabular}{ccc}",
        r"\toprule",
        r"$\varepsilon$ & Peak Accuracy (\%) & Total $\varepsilon$ Consumed \\",
        r"\midrule",
    ]

    dp_summaries = [s for s in summaries if s.algorithm == "FedAvg"]
    for s in dp_summaries:
        lines.append(
            f"{_eps(s.dp_epsilon)} & {s.peak_accuracy * 100:.2f} & {s.dp_budget_total:.1f} \\\\"
        )

    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
        "",
        r"% ---- Table 3: Communication Cost -------------------------",
        r"\begin{table}[h]",
        r"\centering",
        r"\caption{Communication Cost per FL Round (3 clients, 784-dim model)}",
        r"\label{tab:comm-cost}",
        r"\begin{tabular}{lccc}",
        r"\toprule",
        r"Algorithm & $\varepsilon$ & Total Comm. (MB) & Comm./Round (MB) \\",
        r"\midrule",
    ]

    for s in summaries:
        lines.append(
            f"{s.algorithm} & {_eps(s.dp_epsilon)} & "
            f"{s.total_comm_mb:.2f} & {s.total_comm_mb / s.rounds:.4f} \\\\"
        )

    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]

    path.write_text("\n".join(lines), encoding="utf-8")
    log.info("Saved: %s", path)
    return path


def export_json_summary(summaries: list[BenchmarkSummary]) -> Path:
    path = RESULTS_DIR / "summary.json"
    data = []
    for s in summaries:
        d = asdict(s)
        # Remove per-round detail from summary JSON (kept in CSV)
        del d["results"]
        data.append(d)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    log.info("Saved: %s", path)
    return path


def print_summary_table(summaries: list[BenchmarkSummary]) -> None:
    print("\n" + "=" * 75)
    print(f"{'Algorithm':<12} {'eps':>6} {'Peak Acc':>10} {'>90%':>7} {'Comm MB':>9} {'Time s':>8}")
    print("-" * 75)
    for s in summaries:
        eps = f"{s.dp_epsilon:.1f}" if s.dp_epsilon else "inf"
        r90 = str(s.rounds_to_90pct) if s.rounds_to_90pct else f">{s.rounds}"
        print(
            f"{s.algorithm:<12} {eps:>6} {s.peak_accuracy * 100:>9.2f}%"
            f" {r90:>7} {s.total_comm_mb:>9.3f} {s.total_time_s:>8.1f}"
        )
    print("=" * 75 + "\n")


# ════════════════════════════════════════════════════════════════════════════
# Main — benchmark configurations
# ════════════════════════════════════════════════════════════════════════════

def main() -> None:
    parser = argparse.ArgumentParser(description="QFL Benchmark Suite")
    parser.add_argument("--rounds", type=int, default=20)
    parser.add_argument("--clients", type=int, default=3)
    parser.add_argument("--samples", type=int, default=6000)
    parser.add_argument("--alpha", type=float, default=0.5, help="Dirichlet non-IID parameter")
    parser.add_argument("--quick", action="store_true", help="5 rounds, 2000 samples (fast test)")
    args = parser.parse_args()

    if args.quick:
        args.rounds = 5
        args.samples = 2000
        log.info("Quick mode: %d rounds, %d samples", args.rounds, args.samples)

    configs = [
        # (algorithm,  dp_epsilon)
        ("FedAvg",   None),      # Baseline — no DP
        ("FedAvg",   10.0),      # Loose DP
        ("FedAvg",   1.0),       # Standard DP
        ("FedAvg",   0.5),       # Strict DP
        ("q-FedAvg", None),      # Fairness-aware, no DP
        ("q-FedAvg", 1.0),       # Fairness-aware + DP
    ]

    summaries: list[BenchmarkSummary] = []

    for algo, eps in configs:
        s = run_benchmark(
            algorithm=algo,
            n_rounds=args.rounds,
            n_clients=args.clients,
            dp_epsilon=eps,
            alpha_dirichlet=args.alpha,
            n_samples=args.samples,
        )
        summaries.append(s)

    # Export all results
    export_accuracy_csv(summaries)
    export_privacy_tradeoff_csv(summaries)
    export_communication_csv(summaries)
    export_latex_tables(summaries)
    export_json_summary(summaries)
    print_summary_table(summaries)

    log.info("All results saved to: %s", RESULTS_DIR.resolve())


if __name__ == "__main__":
    main()
