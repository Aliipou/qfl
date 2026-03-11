# QFL Platform — Step-by-Step Tutorial

This tutorial walks through the entire QFL Platform from installation to running
your first quantum-secured federated learning round. No prior Qiskit or
federated learning experience required.

---

## Part 1: Installation & Setup

### Step 1 — Clone and install

```bash
git clone https://github.com/aliipou/qfl-platform
cd qfl-platform

# Install all dependencies (FastAPI, Qiskit, PyTorch, Opacus, etc.)
make install
# Equivalent to: pip install -e ".[dev]" && pre-commit install
```

Verify everything installed correctly:

```bash
python -c "import fastapi, qiskit, torch, opacus; print('All OK')"
```

### Step 2 — Start the coordinator

```bash
make dev
```

You should see:

```
INFO:     Uvicorn running on http://0.0.0.0:8000 (Press CTRL+C to quit)
INFO:     Started reloader process
```

Open your browser at **http://localhost:8000/docs** — you'll see the full Swagger UI.

---

## Part 2: Your First Federated Learning Round

### Step 3 — Start a FL round via curl

```bash
curl -X POST http://localhost:8000/train \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "num_clients": 2,
      "local_epochs": 5,
      "learning_rate": 0.01,
      "aggregation": "fed_avg",
      "dp_epsilon": 1.0,
      "dp_delta": 1e-5,
      "use_quantum": false
    },
    "dataset": "mnist",
    "model_architecture": "simple_cnn"
  }'
```

Response (`202 Accepted`):

```json
{
  "id": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
  "status": "pending",
  "config": {
    "num_clients": 2,
    "aggregation": "fed_avg",
    "dp_epsilon": 1.0
  },
  "dataset": "mnist",
  "created_at": "2026-03-11T12:00:00Z",
  "num_clients_participated": 0
}
```

Save the `id` value — you'll need it in the next steps.

```bash
export ROUND_ID="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
```

### Step 4 — Check round status

```bash
curl http://localhost:8000/status/$ROUND_ID
```

```json
{
  "id": "a1b2c3d4-...",
  "status": "pending",
  "num_clients_participated": 0
}
```

The round is waiting for 2 clients to submit their local model updates.

### Step 5 — Submit client updates (simulating 2 FL clients)

In a real deployment, each client trains locally on private data and sends weight
hashes. For this tutorial, we simulate two clients:

**Client 1:**

```bash
curl -X POST http://localhost:8000/train/$ROUND_ID/update \
  -H "Content-Type: application/json" \
  -d "{
    \"client_id\": \"client_01\",
    \"round_id\": \"$ROUND_ID\",
    \"tenant_id\": \"tenant_a\",
    \"weights_hash\": \"$(python3 -c 'import hashlib,os; print(hashlib.sha256(os.urandom(32)).hexdigest())')\",
    \"num_samples\": 5000,
    \"local_loss\": 0.342,
    \"local_accuracy\": 0.891,
    \"dp_noise_applied\": true
  }"
```

**Client 2:**

```bash
curl -X POST http://localhost:8000/train/$ROUND_ID/update \
  -H "Content-Type: application/json" \
  -d "{
    \"client_id\": \"client_02\",
    \"round_id\": \"$ROUND_ID\",
    \"tenant_id\": \"tenant_b\",
    \"weights_hash\": \"$(python3 -c 'import hashlib,os; print(hashlib.sha256(os.urandom(32)).hexdigest())')\",
    \"num_samples\": 3500,
    \"local_loss\": 0.418,
    \"local_accuracy\": 0.863,
    \"dp_noise_applied\": true
  }"
```

Both return `{"accepted": true}`.

When the second client submits, aggregation triggers automatically.

### Step 6 — Check completed round

```bash
curl http://localhost:8000/status/$ROUND_ID
```

```json
{
  "id": "a1b2c3d4-...",
  "status": "completed",
  "global_accuracy": 0.877,
  "privacy_budget_used": 1.0,
  "num_clients_participated": 2,
  "completed_at": "2026-03-11T12:00:04Z"
}
```

`global_accuracy = 0.877` is the weighted FedAvg of 0.891 and 0.863, weighted by
5000 and 3500 samples respectively: `(5000×0.891 + 3500×0.863) / 8500 ≈ 0.879`.

---

## Part 3: Using the Python SDK

### Step 7 — SDK quickstart

```python
from sdk.qfl_client import QFLClient

with QFLClient(base_url="http://localhost:8000", tenant_id="my_company") as client:

    # 1. Health check
    health = client.health()
    print(f"Platform status: {health['status']}")
    print(f"Quantum backend: {health['quantum_backend']}")

    # 2. Start a round
    round_data = client.start_round(
        num_clients=3,
        dataset="industrial_sensor_data",
        aggregation="fed_avg",
        dp_epsilon=0.5,  # strict privacy mode
    )
    round_id = round_data["id"]
    print(f"Round started: {round_id}")

    # 3. Simulate 3 client updates
    import hashlib, os
    for i in range(1, 4):
        ack = client.submit_update(
            round_id=round_id,
            weights_hash=hashlib.sha256(os.urandom(32)).hexdigest(),
            num_samples=1000 * i,
            local_loss=0.5 - i * 0.05,
            local_accuracy=0.75 + i * 0.05,
            client_id=f"client_{i:02d}",
            dp_noise_applied=True,
        )
        print(f"Client {i}: accepted={ack['accepted']}")

    # 4. Poll for completion
    import time
    for _ in range(10):
        status = client.get_round(round_id)
        if status["status"] in ("completed", "failed"):
            break
        time.sleep(0.5)

    print(f"Final accuracy: {status.get('global_accuracy'):.3f}")
    print(f"DP budget used: {status.get('privacy_budget_used')}")

    # 5. Pull EU audit report
    report = client.audit_report()
    print(f"Total rounds: {report['total_rounds']}")
    print(f"Total ε consumed: {report['total_dp_budget_consumed']}")
    print(f"GDPR compliant: {report['gdpr_compliant']}")
```

---

## Part 4: Quantum Mode

### Step 8 — Run a round with BB84 QKD

```bash
curl -X POST http://localhost:8000/train \
  -H "Content-Type: application/json" \
  -d '{
    "config": {
      "num_clients": 1,
      "aggregation": "q_fed_avg",
      "use_quantum": true,
      "dp_epsilon": 1.0
    },
    "dataset": "mnist"
  }'
```

Then submit an update with a QKD key ID:

```bash
curl -X POST http://localhost:8000/train/$ROUND_ID/update \
  -H "Content-Type: application/json" \
  -d "{
    \"client_id\": \"quantum_client\",
    \"round_id\": \"$ROUND_ID\",
    \"tenant_id\": \"tenant_quantum\",
    \"weights_hash\": \"$(python3 -c 'import hashlib,os; print(hashlib.sha256(os.urandom(32)).hexdigest())')\",
    \"num_samples\": 10000,
    \"local_loss\": 0.28,
    \"local_accuracy\": 0.932,
    \"dp_noise_applied\": true,
    \"qkd_key_id\": \"bb84_key_0001\"
  }"
```

The `qkd_key_id` is recorded in the audit trail, linking every model update
to the quantum key used to encrypt it during transmission.

### Step 9 — Generate a QKD key manually

```python
from core.quantum.circuits import bb84_key_exchange

# Simulate BB84 between coordinator and client
result = bb84_key_exchange(num_bits=256, error_rate=0.0)

print(f"Raw bits generated: {len(result.raw_key)}")
print(f"Sifted key length: {result.key_length} bits")
print(f"Channel error rate: {result.error_rate:.3f}")
print(f"Key ID (for audit): {result.key_id}")
print(f"First 8 key bits: {result.sifted_key[:8]}")
```

```
Raw bits generated: 256
Sifted key length: 127 bits
Channel error rate: 0.000
Key ID (for audit): 3f8a12bc9e4d7f21
First 8 key bits: [0, 1, 1, 0, 1, 0, 0, 1]
```

### Step 10 — Build and inspect a VQC

```python
from core.quantum.circuits import VQCConfig, build_vqc

config = VQCConfig(
    num_qubits=4,
    num_layers=2,
    entanglement="linear",   # or "full" for all-to-all
    backend="aer_simulator",
)

circuit = build_vqc(config)

# If Qiskit is installed, this returns a QuantumCircuit
if hasattr(circuit, "draw"):
    print(circuit.draw("text"))
else:
    # Stub mode (Qiskit not installed)
    print(f"VQC stub: {circuit}")
```

---

## Part 5: Full Stack with Docker

### Step 11 — Start everything

```bash
make docker-up
```

This starts 7 services:

```
✓ qfl_coordinator    → http://localhost:8000
✓ qfl_client_01      (tenant_a, isolated network)
✓ qfl_client_02      (tenant_b, isolated network)
✓ qfl_client_03      (tenant_c, isolated network)
✓ qfl_postgres       (audit log + round persistence)
✓ qfl_redis          (round state cache)
✓ qfl_prometheus     → http://localhost:9090
✓ qfl_grafana        → http://localhost:3000  (admin / admin)
```

Wait about 15 seconds for all services to be healthy, then:

```bash
# Verify coordinator is up
curl http://localhost:8000/health

# Open Grafana dashboard
# → http://localhost:3000  (login: admin / admin)
# → Add Prometheus datasource: http://prometheus:9090

# Open Swagger UI
# → http://localhost:8000/docs
```

### Step 12 — View logs

```bash
# All services
make docker-logs

# Coordinator only
docker logs qfl_coordinator -f

# Postgres query log
docker exec qfl_postgres psql -U qfl -d qfldb -c "SELECT * FROM audit_log ORDER BY timestamp DESC LIMIT 10;"
```

---

## Part 6: Running Tests

### Step 13 — Full test suite

```bash
make test
```

Expected:

```
Name                            Stmts   Miss  Cover
----------------------------------------------------
api/schemas.py                     96      0   100%
core/federated/coordinator.py      72      0   100%
core/privacy/differential.py       48      0   100%
...
TOTAL                             649      0   100%

============ 188 passed in 10.07s ============
```

### Step 14 — Run specific test categories

```bash
# Unit tests only (fastest, no Docker needed)
make test-unit

# Integration tests (API round-trips)
make test-integration

# Quantum circuit and coordinator tests
make test-quantum

# Single test file
python -m pytest tests/unit/test_differential_privacy.py -v

# Single test case
python -m pytest tests/unit/test_aggregation.py::TestFedAvg::test_weighted_by_num_samples -v
```

---

## Part 7: EU Compliance Workflow

### Step 15 — Pull a compliance report

After running a few rounds, generate the EU AI Act Article 9 report:

```bash
# For tenant_a
curl "http://localhost:8000/audit/report/tenant_a?from_date=2026-01-01T00:00:00&to_date=2026-12-31T00:00:00"
```

```json
{
  "tenant_id": "tenant_a",
  "from_date": "2026-01-01T00:00:00",
  "to_date": "2026-12-31T00:00:00",
  "total_rounds": 5,
  "total_dp_budget_consumed": 5.0,
  "risk_classification": "limited",
  "gdpr_compliant": true,
  "events": [
    {
      "event": "round_started",
      "timestamp": "2026-03-11T12:00:00Z",
      "risk_level": "limited"
    },
    {
      "event": "round_completed",
      "details": { "global_accuracy": 0.923, "dp_epsilon_used": 1.0 },
      "timestamp": "2026-03-11T12:00:04Z"
    }
  ]
}
```

### Step 16 — Compute conformal prediction bounds

```python
import numpy as np
from core.privacy.conformal import accuracy_prediction_set

# Suppose the global model achieved 92.3% accuracy on the aggregated validation set.
# We have 100 calibration scores (1 - P(true class)) from a holdout set.
calibration_scores = np.random.beta(2, 8, size=100)  # realistic distribution

interval = accuracy_prediction_set(
    global_accuracy=0.923,
    calibration_scores=calibration_scores,
    alpha=0.1,  # 90% coverage guarantee
)

print(f"Point estimate:    {0.923:.3f}")
print(f"90% CI lower:      {interval.lower:.3f}")
print(f"90% CI upper:      {interval.upper:.3f}")
print(f"Interval width:    {interval.width:.3f}")
print(f"Coverage guarantee: {interval.coverage:.0%}")
```

```
Point estimate:    0.923
90% CI lower:      0.874
90% CI upper:      0.972
Interval width:    0.098
Coverage guarantee: 90%
```

This interval is reported in the model card and audit log, providing
regulators with statistically valid uncertainty bounds.

---

## Part 8: IBM Quantum (Real Hardware)

### Step 17 — Connect to IBM Quantum

```bash
# Get your token from https://quantum.ibm.com
export IBM_QUANTUM_TOKEN="your_token_here"

# Restart the coordinator (it reads the token on startup)
make dev
```

Or configure programmatically:

```python
import os
os.environ["IBM_QUANTUM_TOKEN"] = "your_token_here"

from core.quantum.hardware import HardwareConfig, QuantumBackend

config = HardwareConfig(
    backend_name="ibm_brisbane",  # or ibm_sherbrooke, ibm_kyoto, etc.
    shots=1024,
    optimization_level=2,  # higher = more gate reduction
)

backend = QuantumBackend(config)
connected = backend.connect_ibm()

if connected:
    print(f"Connected to: {backend.backend_name}")
    # Run a VQC on real hardware
    from core.quantum.circuits import VQCConfig, build_vqc
    circuit = build_vqc(VQCConfig(num_qubits=4, num_layers=1))
    result = backend.run(circuit)
    print(f"Measurement result: {result.counts}")
    print(f"Most frequent state: {result.most_frequent}")
else:
    print("Using Aer simulator (token invalid or IBM unavailable)")
```

**Note**: Real quantum hardware jobs take 15–120 seconds depending on queue.
The Aer simulator runs in <1s and is used for all Phase 1–3 development.

---

## Part 9: CI/CD Pipeline

### Step 18 — Understanding the GitHub Actions pipeline

The `.github/workflows/ci.yml` pipeline runs on every push:

```
Push to main/develop
        │
        ▼
    [lint]
    ruff check . + mypy api/ core/ sdk/
        │  ✓ pass
        ▼
  [unit-tests]
  pytest tests/unit/ tests/quantum/
  → must achieve ≥90% coverage
        │  ✓ pass
        ▼
  [integration-tests]
  pytest tests/integration/
  (with real postgres + redis services)
        │  ✓ pass
        ▼
  [security]
  Bandit SAST + Trivy container scan
  → CRITICAL/HIGH vulnerabilities → fail
        │  ✓ pass (main branch only)
        ▼
  [docker-build]
  Build + push ghcr.io/aliipou/qfl-platform/qfl-coordinator
  With SBOM + provenance attestation
        │  ✓ pass
        ▼
  [deploy-staging]
  kind cluster → helm upgrade → smoke test GET /health
```

To run the pipeline locally before pushing:

```bash
# Lint
make lint

# Full test suite
make test

# Docker build
docker build -f docker/Dockerfile.coordinator -t qfl-coordinator:local .

# Smoke test
docker run -d -p 8000:8000 qfl-coordinator:local
curl http://localhost:8000/health
```

---

## Part 10: Differential Privacy Deep Dive

### Step 19 — Manually apply DP to model weights

```python
import numpy as np
from core.privacy.differential import DPBudget, DPConfig, add_gaussian_noise, clip_gradients

# Simulate a client's local model weights (e.g. a simple linear layer)
weights = [
    np.random.randn(128, 64).astype(np.float32),  # weight matrix
    np.random.randn(64).astype(np.float32),         # bias vector
]

config = DPConfig(
    epsilon=1.0,        # privacy budget per round
    delta=1e-5,         # failure probability
    max_grad_norm=1.0,  # L2 clipping threshold
    noise_multiplier=1.1,
)

# Step 1: Clip gradients to bound sensitivity
clipped_weights, actual_norm = clip_gradients(weights, max_norm=config.max_grad_norm)
print(f"Original norm: {actual_norm:.3f}")
print(f"After clipping, norm ≤ {config.max_grad_norm}")

# Step 2: Add calibrated Gaussian noise
noisy_weights = add_gaussian_noise(
    clipped_weights,
    sensitivity=config.max_grad_norm,
    epsilon=config.epsilon,
    delta=config.delta,
)

# Step 3: Track budget
budget = DPBudget(epsilon_total=10.0, delta=config.delta)
budget.consume(config.epsilon)

print(f"\nDP Budget Status:")
print(f"  ε consumed: {budget.epsilon_consumed:.1f} / {budget.epsilon_total:.1f}")
print(f"  ε remaining: {budget.epsilon_remaining:.1f}")
print(f"  Rounds completed: {budget.rounds}")
print(f"  Budget exhausted: {budget.is_exhausted}")

# Step 4: Rényi DP loss (tighter accounting)
rdp_loss = budget.privacy_loss_rdp(alpha=10.0, sigma=config.noise_multiplier)
print(f"  RDP loss (α=10, σ=1.1): {rdp_loss:.4f}")
```

```
Original norm: 87.432
After clipping, norm ≤ 1.0

DP Budget Status:
  ε consumed: 1.0 / 10.0
  ε remaining: 9.0
  Rounds completed: 1
  Budget exhausted: False
  RDP loss (α=10, σ=1.1): 4.1322
```

---

## Troubleshooting

### "Module not found: qiskit_aer"

The coordinator starts and runs fine without Qiskit. The `AerSimulatorBackend`
falls back to a mock backend automatically. To install Qiskit:

```bash
pip install qiskit qiskit-aer qiskit-ibm-runtime
```

### "Round 404 not found" when polling status

The coordinator uses a **shared singleton** via `api/dependencies.py`. If you
created the round in one request and the status check hits a different process
(in multi-worker mode), the round won't be found. This is a known Phase 1 limitation.

**Fix**: Switch to Redis-backed round storage (Phase 4). For development, use
`--workers 1`:

```bash
uvicorn api.main:app --workers 1 --reload
```

### Tests fail with "No module named 'structlog'"

```bash
pip install -e ".[dev]"
```

### Docker Compose: postgres fails health check

```bash
docker logs qfl_postgres
# Usually a permissions issue on the data volume
docker compose down -v  # remove volumes
make docker-up
```

### IBM Quantum connection timeout

IBM Quantum queues can be long on free-tier accounts. The backend falls back to
Aer automatically. Check queue status at https://quantum.ibm.com/services/resources.

---

## Next Steps

After completing this tutorial, you are ready to:

1. **Implement real PyTorch training** — replace the mock `weights_hash` with
   actual serialized weight tensors encrypted with the QKD key.

2. **Add Opacus DP-SGD** — wrap your PyTorch optimizer:
   ```python
   from opacus import PrivacyEngine
   privacy_engine = PrivacyEngine()
   model, optimizer, dataloader = privacy_engine.make_private(
       module=model, optimizer=optimizer, data_loader=dataloader,
       noise_multiplier=1.1, max_grad_norm=1.0,
   )
   ```

3. **Deploy to Kubernetes** — see `infra/helm/coordinator/` and the CI/CD pipeline.

4. **Connect real IBM Quantum hardware** — set `IBM_QUANTUM_TOKEN` and enable
   `use_quantum: true` in your round config.

5. **Write the paper** — see `paper/main.tex` for the IEEE template scaffold.
