# QFL Platform — Architecture Reference

## Overview

QFL Platform is organized into four concentric layers. Each layer depends only on
the layers below it, making components independently testable and replaceable.

```
┌─────────────────────────────────────────────────────────┐
│  Layer 4 — Infrastructure                               │
│  Kubernetes · Helm · Docker · GitHub Actions · Nginx    │
├─────────────────────────────────────────────────────────┤
│  Layer 3 — EU Compliance Engine                         │
│  Audit Trail · DP Budget Ledger · GDPR · Model Cards    │
├─────────────────────────────────────────────────────────┤
│  Layer 2 — Federated Learning Orchestration             │
│  FLCoordinator · FedAvg · q-FedAvg · FL Clients         │
├─────────────────────────────────────────────────────────┤
│  Layer 1 — Quantum Privacy Core                         │
│  BB84 QKD · VQC · IBM Quantum Runtime · Aer Simulator   │
└─────────────────────────────────────────────────────────┘
```

---

## Layer 1 — Quantum Privacy Core

### BB84 Quantum Key Distribution (`core/quantum/circuits.py`)

The BB84 protocol (Bennett & Brassard, 1984) is the first and most widely deployed
quantum cryptographic protocol. It provides information-theoretic security: an
eavesdropper cannot intercept the key without introducing detectable errors.

**Protocol steps in QFL:**

```
Alice (Coordinator)                     Bob (FL Client)
─────────────────────────────────────────────────────
1. Generate N random bits:   0 1 0 0 1 1 0 1 ...
2. Choose random bases (+/×): + × + × + × × + ...
3. Encode qubits and send ──────────────────────►
                                        4. Measure in random bases
                                        5. Announce bases (classical channel)
6. Announce bases ◄──────────────────────────────
7. Sifting: keep matching basis positions only
   Sifted key: ~50% of raw bits
8. Error rate check: >25% → eavesdropper detected, abort
9. Sifted key → AES-256 encryption of FL weight updates
```

**Implementation** (`bb84_key_exchange`):
- `num_bits`: raw bits to generate (default 256, sifted ≈ 128 bits)
- `error_rate`: simulated channel noise (0.0 = perfect, 0.11 = practical limit)
- Returns `BB84Result` with `sifted_key`, `key_length`, `error_rate`, `key_id`
- `key_id` is a 16-char hex identifier for audit trail correlation

**Phase 2 upgrade**: replace simulation with real IBM Quantum measurement.

---

### Variational Quantum Circuit — VQC (`core/quantum/circuits.py`)

The VQC is a hybrid classical-quantum model component. The circuit is parameterized;
parameters are updated by classical gradient descent (PyTorch autograd).

```
Qubit 0: ─[RY(θ₀)]─[RZ(θ₁)]─●──────────────
Qubit 1: ─[RY(θ₂)]─[RZ(θ₃)]─⊕─●────────────  (linear entanglement)
Qubit 2: ─[RY(θ₄)]─[RZ(θ₅)]───⊕─●──────────
Qubit 3: ─[RY(θ₆)]─[RZ(θ₇)]─────⊕──[measure]
          Layer 1               CNOT gates
```

- `num_qubits`: 4 (default) — scales quadratically in gate count for `full` entanglement
- `num_layers`: 2 (default) — each layer adds one RY/RZ block + entanglement
- `entanglement`: `"linear"` (nearest-neighbor) or `"full"` (all-to-all)
- Returns `QuantumCircuit` if Qiskit installed, otherwise a stub dict (graceful fallback)

---

### IBM Quantum Backend (`core/quantum/hardware.py`)

```python
QuantumBackend
├── connect_ibm()          # Reads IBM_QUANTUM_TOKEN, connects via QiskitRuntimeService
├── run(circuit)           # Dispatches to IBM or Aer based on connection state
├── _run_ibm(circuit)      # SamplerV2 Primitives API, transpile + execute
└── _simulator.run(circuit) # Aer fallback (always available)
```

**Decision flow:**

```
run(circuit) called
      │
      ▼
_ibm_backend is set?
      │
   Yes│         No
      ▼          ▼
_run_ibm()   _simulator.run()
      │
   fails?
      │
   Yes│
      ▼
_simulator.run() (fallback)
```

The fallback ensures the coordinator never crashes due to IBM Quantum availability.

---

## Layer 2 — Federated Learning Orchestration

### FL Round Lifecycle

```
POST /train  →  FLCoordinator.create_round()
                      │
                      ▼
              FLRound(status=PENDING)
                      │
              clients submit updates via
              POST /train/{round_id}/update
                      │
                      ▼
              status = RUNNING (first update received)
                      │
              all num_clients submitted?
                      │
                   Yes│
                      ▼
              status = AGGREGATING
              _aggregate() called (asyncio task)
                      │
                      ▼
         FedAvg or q-FedAvg on weight arrays
         + DP budget recorded
         + AuditLog entry written
                      │
                      ▼
              status = COMPLETED | FAILED
```

### FedAvg Algorithm (`core/federated/aggregation.py`)

McMahan et al. (2017) — Communication-Efficient Learning of Deep Networks from Decentralized Data.

```
global_weights = Σᵢ (nᵢ / N) × wᵢ

where:
  wᵢ  = client i's local model weights
  nᵢ  = client i's number of training samples
  N   = Σ nᵢ (total samples across all clients)
```

Clients with more data have higher influence — this is the correct behavior for
heterogeneous data distributions common in industrial IoT settings.

### q-FedAvg Algorithm (`core/federated/aggregation.py`)

Li et al. (2020) — Fair Resource Allocation in Federated Learning.

```
Higher q → clients with worse loss get more weight
q = 0    → equivalent to FedAvg
q = 2    → recommended default for fairness
```

**Phase 3 implementation note**: The Phase 1 stub delegates to FedAvg. Phase 3 will
add per-client loss values to `ClientUpdate` and implement the full reweighting:

```python
hᵢ = |∇Fᵢ(w)| / (learning_rate)^q   # gradient magnitude weighted by fairness param
w_new = w - Σᵢ hᵢ(wᵢ - w) / Σᵢ hᵢ  # q-FedAvg update rule
```

---

## Layer 3 — EU Compliance Engine

### Differential Privacy (`core/privacy/differential.py`)

**Gaussian mechanism** for (ε, δ)-differential privacy:

```
σ = sensitivity × √(2 × ln(1.25 / δ)) / ε

Noise: n ~ N(0, σ²) added to each weight tensor component
```

**Gradient clipping** (required before noise injection in DP-SGD):

```
w_clipped = w × min(1, C / ‖w‖₂)

where C = max_grad_norm (sensitivity parameter)
```

The clipping bounds gradient sensitivity — without it, a single outlier data point
could dominate and ε becomes meaningless.

**DPBudget** tracks cumulative ε across all rounds. When `epsilon_total` is exhausted,
the tenant must wait before submitting further rounds. This enforces the EU AI Act
requirement for documented privacy guarantees.

### Conformal Prediction (`core/privacy/conformal.py`)

Conformal prediction provides **distribution-free coverage guarantees** on the
global model's accuracy, requiring no distributional assumptions.

```
Calibration set → nonconformity scores sᵢ = 1 - P(true class | xᵢ)
                                                │
Threshold τ = quantile(s, ⌈(n+1)(1-α)⌉/n)      │
                                                ▼
Prediction set C(x) = {y : s(x,y) ≤ τ}

Guarantee: P(y* ∈ C(x)) ≥ 1 - α
```

For the global FL model accuracy `â`, the platform computes:

```
uncertainty = τ / 2
CI = [max(0, â - uncertainty), min(1, â + uncertainty)]
```

This gives EU-auditable bounds on what the model can and cannot reliably predict.

### Audit Logger (`core/privacy/audit.py`)

Every significant event produces an immutable `AuditLog` entry:

| Event | Trigger |
|---|---|
| `round_started` | `POST /train` |
| `client_joined` | First update received |
| `client_update_received` | Each `POST /train/{id}/update` |
| `aggregation_completed` | After FedAvg/q-FedAvg |
| `round_completed` | After accuracy computed |
| `round_failed` | On any exception in aggregation |
| `dp_budget_consumed` | After each round |
| `model_deployed` | Future: production deployment |
| `erasure_request` | GDPR Article 17 trigger |

**PostgreSQL enforcement**: `CREATE RULE no_update_audit / no_delete_audit`
makes the audit table append-only at the database level — even a compromised
application cannot alter historical entries.

---

## Layer 4 — Infrastructure

### Network Architecture

```
Internet
    │
    ▼
Nginx (443 TLS 1.3)
  ├── Rate limit: 50 req/min (general), 10 req/min (/train)
  ├── Security headers: HSTS 2yr, CSP, X-Frame-Options, nosniff
  └── Proxy → coordinator:8000
          │
          ▼
    Coordinator (FastAPI, 4 workers)
          │
     ┌────┴────┐
     ▼         ▼
PostgreSQL    Redis
(audit log)  (round state)

Tenant networks (isolated):
  tenant_a_net ──► client_01 (can only reach coordinator)
  tenant_b_net ──► client_02 (cannot reach tenant_a_net)
  tenant_c_net ──► client_03 (cannot reach tenant_b_net)
```

### Kubernetes NetworkPolicy

The `default-deny-all` policy blocks all traffic by default. Exceptions are
explicitly whitelisted:

```
coordinator → postgres (port 5432) ✓
coordinator → redis    (port 6379) ✓
tenant_a   → coordinator (port 8000) ✓
tenant_a   → tenant_b ✗  BLOCKED
tenant_b   → tenant_a ✗  BLOCKED
```

This maps directly to the multi-tenancy model from the thesis work on Kubernetes
namespace isolation.

---

## Data Flow: Full FL Round

```
1. Operator calls POST /train
   └── FLRound created, AuditEvent.ROUND_STARTED logged

2. Each FL client:
   a. Pulls round config from GET /status/{round_id}
   b. Trains locally for local_epochs on private data
   c. Applies DP-SGD: clip gradients + add Gaussian noise
   d. Encrypts weights using QKD key (bb84_key_id)
   e. Submits POST /train/{round_id}/update with weights_hash

3. Coordinator receives updates:
   └── AuditEvent.CLIENT_UPDATE_RECEIVED per client

4. When all num_clients have submitted:
   a. FedAvg or q-FedAvg aggregation
   b. Conformal prediction interval computed
   c. AuditEvent.ROUND_COMPLETED with global_accuracy + dp_epsilon_used
   d. Model card generated

5. Operator queries GET /status/{round_id}
   └── Returns global_accuracy, privacy_budget_used, completed_at

6. EU auditor queries GET /audit/report/{tenant_id}
   └── Returns full compliance report: all events, total DP budget, GDPR status
```
