"""
Generate publication-quality figures from benchmark CSV results.
Run after: python -m benchmarks.fl_benchmark --rounds 20

Outputs (in paper/figures/):
  accuracy_vs_rounds.pdf   — Figure 1 (accuracy over FL rounds)
  privacy_tradeoff.pdf     — Figure 2 (privacy-utility curve)
  comm_cost.pdf            — Figure 3 (communication overhead)
"""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

RESULTS = Path(__file__).parents[2] / "benchmarks" / "results"
FIGURES = Path(__file__).parent

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker as mticker
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    print("matplotlib not installed. Run: pip install matplotlib")

# IEEE double-column figure width
FIG_W = 3.5   # inches (single column)
FIG_H = 2.6


def ieee_style(ax: "plt.Axes") -> None:
    """Apply IEEE-publication-quality styling."""
    ax.grid(True, linestyle="--", linewidth=0.5, alpha=0.6)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    for spine in ax.spines.values():
        spine.set_linewidth(0.8)
    ax.tick_params(labelsize=8)
    ax.xaxis.label.set_size(9)
    ax.yaxis.label.set_size(9)
    ax.title.set_size(9)


STYLE_MAP = {
    # (algorithm, dp_epsilon) → (label, color, linestyle, marker)
    ("FedAvg",   "None"):  ("FedAvg (no DP)",       "#1f77b4", "-",  "o"),
    ("FedAvg",   "10.0"):  ("FedAvg (ε=10)",         "#ff7f0e", "--", "s"),
    ("FedAvg",   "1.0"):   ("FedAvg (ε=1)",          "#d62728", "-.", "^"),
    ("FedAvg",   "0.5"):   ("FedAvg (ε=0.5)",        "#9467bd", ":",  "D"),
    ("q-FedAvg", "None"):  ("q-FedAvg (no DP)",      "#2ca02c", "-",  "v"),
    ("q-FedAvg", "1.0"):   ("q-FedAvg (ε=1)",        "#8c564b", "--", "P"),
}


# ─────────────────────────────────────────────────────────────
# Figure 1: Accuracy vs Rounds
# ─────────────────────────────────────────────────────────────

def plot_accuracy_vs_rounds() -> None:
    path = RESULTS / "accuracy_vs_rounds.csv"
    if not path.exists():
        print(f"Not found: {path} — run benchmarks first")
        return

    data: dict[tuple, list] = defaultdict(list)
    with open(path) as f:
        for row in csv.DictReader(f):
            key = (row["algorithm"], row["dp_epsilon"])
            data[key].append((int(row["round"]), float(row["global_accuracy"])))

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    for key, points in sorted(data.items()):
        if key not in STYLE_MAP:
            continue
        label, color, ls, marker = STYLE_MAP[key]
        rounds = [p[0] for p in points]
        accs = [p[1] * 100 for p in points]
        ax.plot(rounds, accs, label=label, color=color,
                linestyle=ls, marker=marker, markersize=4, linewidth=1.2)

    ax.set_xlabel("FL Round")
    ax.set_ylabel("Global Accuracy (%)")
    ax.set_title("Accuracy vs. FL Rounds (MNIST, non-IID α=0.5)")
    ax.legend(fontsize=6.5, loc="lower right", framealpha=0.9)
    ax.set_ylim(0, 105)
    ieee_style(ax)
    fig.tight_layout()

    out = FIGURES / "accuracy_vs_rounds.pdf"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    print(f"Saved: {out}")
    plt.close(fig)


# ─────────────────────────────────────────────────────────────
# Figure 2: Privacy-Utility Tradeoff
# ─────────────────────────────────────────────────────────────

def plot_privacy_tradeoff() -> None:
    path = RESULTS / "privacy_sweep.csv"
    if not path.exists():
        # Fall back to privacy_tradeoff.csv from main benchmark
        path = RESULTS / "privacy_tradeoff.csv"
    if not path.exists():
        print(f"Not found: {path} — run benchmarks first")
        return

    epsilons, accs = [], []
    with open(path) as f:
        for row in csv.DictReader(f):
            eps_raw = row.get("epsilon_config") or row.get("dp_epsilon", "")
            acc_raw = row.get("peak_accuracy", "0")
            if "None" in eps_raw or "inf" in eps_raw.lower():
                eps_val = 100.0   # plot as "no DP" reference line
            else:
                try:
                    eps_val = float(eps_raw)
                except ValueError:
                    continue
            epsilons.append(eps_val)
            accs.append(float(acc_raw) * 100)

    if not epsilons:
        print("No data in privacy tradeoff CSV")
        return

    fig, ax = plt.subplots(figsize=(FIG_W, FIG_H))

    # No-DP reference line
    no_dp_acc = next((a for e, a in zip(epsilons, accs) if e >= 50), None)
    if no_dp_acc:
        ax.axhline(no_dp_acc, color="gray", linestyle=":", linewidth=1,
                   label=f"No DP baseline ({no_dp_acc:.1f}%)")

    # DP points
    dp_eps = [(e, a) for e, a in zip(epsilons, accs) if e < 50]
    if dp_eps:
        dp_eps.sort()
        xs = [e for e, _ in dp_eps]
        ys = [a for _, a in dp_eps]
        ax.plot(xs, ys, "o-", color="#1f77b4", linewidth=1.5,
                markersize=5, label="FedAvg + DP (δ=1e-5)")
        ax.fill_between(xs, [y - 2 for y in ys], [y + 2 for y in ys],
                        alpha=0.15, color="#1f77b4")

    ax.set_xscale("log")
    ax.set_xlabel("Privacy Budget ε (log scale)")
    ax.set_ylabel("Peak Accuracy (%)")
    ax.set_title("Privacy-Utility Tradeoff")
    ax.legend(fontsize=7, framealpha=0.9)
    ieee_style(ax)
    fig.tight_layout()

    out = FIGURES / "privacy_tradeoff.pdf"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    print(f"Saved: {out}")
    plt.close(fig)


# ─────────────────────────────────────────────────────────────
# Figure 3: Communication Cost Bar Chart
# ─────────────────────────────────────────────────────────────

def plot_comm_cost() -> None:
    path = RESULTS / "communication_cost.csv"
    if not path.exists():
        print(f"Not found: {path}")
        return

    rows = []
    with open(path) as f:
        for row in csv.DictReader(f):
            rows.append(row)

    labels = [
        f"{r['algorithm']}\n(ε={r['dp_epsilon'][:4]})"
        for r in rows
    ]
    per_round = [float(r["comm_per_round_mb"]) for r in rows]
    colors = ["#1f77b4" if "FedAvg" in r["algorithm"] and "q" not in r["algorithm"]
              else "#2ca02c" for r in rows]

    fig, ax = plt.subplots(figsize=(FIG_W + 0.5, FIG_H))
    bars = ax.bar(range(len(labels)), per_round, color=colors,
                  edgecolor="black", linewidth=0.5, width=0.6)

    for bar, val in zip(bars, per_round):
        ax.text(bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.02,
                f"{val:.3f}", ha="center", va="bottom", fontsize=7)

    ax.set_xticks(range(len(labels)))
    ax.set_xticklabels(labels, fontsize=7)
    ax.set_ylabel("Communication per Round (MB)")
    ax.set_title("Communication Cost per FL Round")
    ieee_style(ax)
    fig.tight_layout()

    out = FIGURES / "comm_cost.pdf"
    fig.savefig(out, dpi=300, bbox_inches="tight")
    print(f"Saved: {out}")
    plt.close(fig)


# ─────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if not MATPLOTLIB_AVAILABLE:
        raise SystemExit("Install matplotlib: pip install matplotlib")

    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "DejaVu Serif"],
        "text.usetex": False,
        "figure.dpi": 150,
    })

    print("Generating publication figures...")
    plot_accuracy_vs_rounds()
    plot_privacy_tradeoff()
    plot_comm_cost()
    print("Done. Include in LaTeX with: \\includegraphics{figures/accuracy_vs_rounds.pdf}")
