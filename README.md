<div align="center">

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?style=flat&logo=python)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green?style=flat)](LICENSE)

# qfl — Trustworthy Distributed Intelligence (research platform)

**An independent research platform for trustworthy distributed intelligence under adversarial conditions** — federated learning, privacy, cryptographic agility, and adversarial robustness. *Quantum communication is one interchangeable provider, not the foundation of the architecture.*

</div>

## What this is

`qfl` (historically "Quantum Federated Learning") is a **research platform** — not a production system, and not a quantitative-finance library. Concretely it is a FastAPI coordination server for federated-learning rounds: clients train locally and submit weight updates; the coordinator aggregates them (FedAvg / Q-FedAvg) without seeing raw data. It investigates three questions:

1. **Train without sharing raw data** — federated learning.
2. **Establish trust** — audit, provenance, differential privacy, secure aggregation.
3. **Survive attack** — Byzantine clients, poisoning, backdoors, model stealing.

Security/transport is a **pluggable provider**, deliberately interchangeable so the platform outlives any single technology:

```
Research core (FL · privacy · aggregation · audit)
        │  Provider interface
        ├── Classical TLS
        ├── PQC (post-quantum)
        ├── BB84 / QKD  — simulation only (research tier, T3)
        └── future (MPC, TEE, …)
```

> **Honest status:** there is **no real quantum security today**. BB84/QKD here is a Phase-2 *simulation* (research tier). If the goal is post-quantum banking, that belongs in AuthGate's PQC provider — **not** in qfl.

## Architecture

```
FL Clients (K nodes)
    │  POST /train/{round_id}/update  (weight deltas)
    ▼
┌─────────────────────────────────────────────────┐
│              QFL Coordinator (FastAPI)           │
│                                                 │
│  POST /train          → create FL round         │
│  POST /train/{id}/update → accept client update │
│  GET  /status/{id}   → poll round progress      │
│  GET  /audit         → privacy budget log       │
│  GET  /health        → liveness check           │
│                                                 │
│  core/federated/coordinator.py                  │
│    FLCoordinator — manages rounds, collects     │
│    client updates, triggers aggregation         │
│                                                 │
│  core/federated/aggregation.py                  │
│    fed_avg()  — classical FedAvg                │
│    q_fed_avg() — quantum-weighted variant       │
│                                                 │
│  core/privacy/differential.py                   │
│    DPBudget — ε/δ tracking across rounds        │
│    dp_noise() — Gaussian noise injection        │
│                                                 │
│  core/privacy/conformal.py                      │
│    Conformal prediction intervals               │
│                                                 │
│  core/quantum/circuits.py                       │
│    BB84 QKD simulation (Phase 2 scaffold)       │
│    VQC circuit stubs                            │
└─────────────────────────────────────────────────┘
    │
    ▼
SDK (sdk/qfl_client/)  — Python client library
    Wraps /train and /status over HTTP
```

## Quick Start

```bash
pip install -e ".[dev]"
uvicorn api.main:app --reload
```

API docs at [http://localhost:8000/docs](http://localhost:8000/docs).

### Create and run an FL round

```python
from sdk.qfl_client import QFLClient
import httpx

client = QFLClient(base_url="http://localhost:8000")

# Coordinator: create a round
round_obj = client.create_round(
    dataset="mnist",
    model_architecture="cnn_small",
    config={"min_clients": 3, "aggregation": "fedavg", "rounds": 5},
)

# Client: submit a weight update
client.submit_update(
    round_id=round_obj["id"],
    weights=[0.1, -0.3, 0.7],   # flattened model delta
    num_samples=1000,
    client_id="client-42",
)

# Poll for completion
status = client.get_status(round_obj["id"])
print(status["status"])  # "completed" | "in_progress" | "failed"
```

## Privacy Budget

Each FL round consumes differential privacy budget (ε, δ). Track it via the audit endpoint:

```bash
curl http://localhost:8000/audit
```

Returns consumed ε per round and remaining budget.

## What Is Implemented vs Planned

| Component | Status |
|-----------|--------|
| FL coordinator (in-memory rounds) | Done |
| FedAvg aggregation | Done |
| DP-SGD noise injection + ε/δ tracking | Done |
| Conformal prediction intervals | Done |
| REST API + SDK | Done |
| BB84 QKD simulation | Phase 2 scaffold |
| Real quantum hardware (IBM Runtime) | Phase 3 — not yet |
| Redis + PostgreSQL persistence | Phase 4 — not yet |
| KEDA autoscaling | Not yet |

## Run Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

## License

MIT
