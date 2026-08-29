# qfl — red-team findings (federated aggregation)

Research-tier. The aggregator `core.federated.aggregation.fed_avg` is plain weighted
averaging with no robustness. The red-team (`tests/test_redteam_fl_aggregation.py`)
mounts real federated-learning attacks; results:

| Attack | Status |
|--------|--------|
| Model poisoning (one client, huge weights) | ❌ **VULNERABLE** — single client dominates the global model |
| Sample-count inflation | ❌ **VULNERABLE** — attacker lies about `num_samples` and seizes the aggregation weight |
| NaN injection | ❌ **VULNERABLE** — a NaN update corrupts the entire aggregate |
| Inf injection | ❌ **VULNERABLE** — an Inf update corrupts the entire aggregate |
| Zero total samples | ✅ rejected (`ValueError`) |

These are expected for plain FedAvg — it was never Byzantine-robust. They are pinned
as `test_VULN_*`; if one starts failing, a defense was added (update this file).

## Mitigation (future work — not implemented, no feature creep here)

- **Robust aggregation**: coordinate-wise median, trimmed mean, or Krum instead of mean.
- **Per-client norm clipping** before averaging.
- **Input sanitization**: reject NaN/Inf, bound declared sample counts.
- **Client authentication**: only accept updates from capability-bearing clients —
  this is exactly what AuthGate provides, consumed by qfl, not reimplemented here.

Until then: **qfl's aggregation must not be used where clients are untrusted.**
