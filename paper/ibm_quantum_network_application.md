# IBM Quantum Network — Member Application

**Program**: IBM Quantum Network (Academic / Startup track)
**Applicant**: Ali Pourrahim
**Institution**: Centria University of Applied Sciences, Finland
**Contact**: ali.pourrahim@centria.fi
**Project URL**: https://github.com/aliipou/qfl-platform

---

## Executive Summary

I am applying for IBM Quantum Network membership to support **QFL Platform**,
the first production-ready Quantum Federated Learning middleware integrating
BB84 QKD, variational quantum circuits, and EU AI Act compliance. I request
access to IBM Eagle r3 backends (ibm_brisbane / ibm_sherbrooke) for hardware
validation of quantum circuit components in a real federated learning setting.

---

## Project Description

### What is QFL?

QFL Platform is an open-source middleware that runs real federated learning
rounds secured by quantum cryptography. Three industrial tenants train models
on private data; updates are encrypted via BB84 QKD keys generated on IBM
Quantum hardware; a variational quantum circuit serves as a hybrid model
component; the EU AI Act compliance engine produces immutable audit trails.

This is not a simulation study. QFL is a deployable system:
- FastAPI coordinator with REST API
- Kubernetes-native (Helm charts, NetworkPolicy tenant isolation)
- 100% test coverage, GitHub Actions CI/CD
- pip-installable Python SDK

### Why IBM Quantum hardware is essential

The critical gap between our current work and a publication-quality result is
**real hardware validation**. Specifically:

| Experiment | Requires IBM Hardware |
|---|---|
| BB84 QKD bit error rate on real quantum channel | Yes |
| VQC gate fidelity on Eagle r3 vs Aer simulator | Yes |
| Hardware noise as implicit regularization in FL | Yes |
| Latency benchmark: quantum circuit in FL round | Yes |
| Quantum advantage claim validation | Yes |

These experiments cannot be replicated on Aer simulator because simulator
results have 0% gate error, 0% readout error, and 0ms queue time —
fundamentally different from real quantum computation.

### Target publication

**Title**: QFL: A Production-Ready Quantum Federated Learning Framework
with EU AI Act Compliance and Differential Privacy

**Target venue**: IEEE Transactions on Quantum Engineering or
IEEE International Conference on Quantum Computing and Engineering (QCE)

**arXiv preprint**: planned for submission after hardware validation

**Timeline**: arXiv submission within 60 days of hardware access

---

## Technical Approach

### Phase 2 (current): IBM Quantum integration

```python
# Already implemented in core/quantum/hardware.py
from core.quantum.hardware import HardwareConfig, QuantumBackend

config = HardwareConfig(
    backend_name="ibm_brisbane",
    shots=1024,
    optimization_level=2,
)
backend = QuantumBackend(config)
backend.connect_ibm()  # awaiting IBM_QUANTUM_TOKEN
```

The connector implements the Primitives API (SamplerV2) with automatic
transpilation and Aer fallback — no code changes needed, only hardware access.

### Quantum experiments planned

**Experiment 1 — BB84 QKD on real hardware**
- Implement BB84 basis encoding on 1-qubit circuits
- Measure bit error rate across 1000 key exchange simulations
- Compare: real hardware BER vs channel noise model

**Experiment 2 — VQC fidelity benchmark**
- Run 4-qubit VQC (2 layers, linear entanglement) on ibm_brisbane
- Compare measurement distribution: Aer vs real hardware
- Report gate fidelity and readout error impact on FL model accuracy

**Experiment 3 — End-to-end QFL round with real hardware**
- 3-client FL round with VQC component on IBM hardware
- Measure: latency per round, accuracy impact of hardware noise
- Benchmark against classical FedAvg

**Experiment 4 — Quantum amplitude estimation for q-FedAvg**
- Implement quantum amplitude estimation for loss-weighted aggregation
- Validate correctness vs classical weighted average
- Measure circuit depth and T-gate count

### Resources requested

| Resource | Requested | Justification |
|---|---|---|
| Backend | ibm_brisbane (127q Eagle r3) | Largest available, needed for multi-qubit VQC |
| Shots per job | 1024–8192 | Statistical significance for BER experiments |
| Monthly jobs | ~500 | 4 experiments × replications × parameter sweep |
| Duration | 6 months | Paper submission + defense preparation |

---

## Researcher Background

**Ali Pourrahim** is a Bachelor's student at Centria University of Applied
Sciences (Kokkola, Finland), specializing in distributed systems and
quantum computing. Prior work includes:

- Multi-tenant Kubernetes network isolation (thesis project, validated with
  NetworkPolicy enforcement — the same architecture powers QFL's tenant
  isolation layer)
- FastAPI microservices deployed in production
- Independent study of Qiskit, quantum cryptography, and federated learning

QFL was built as an independent research project demonstrating readiness for
graduate-level research. The project is the basis for PhD applications to
Nordic and EU universities for Fall 2027.

**GitHub**: github.com/aliipou
**Project**: github.com/aliipou/qfl-platform

---

## EU/Nordic Relevance

QFL directly addresses priorities of the Finnish national quantum strategy
and the EU Quantum Flagship program:

- **EU AI Act compliance**: QFL is the only FL framework designed around
  Article 9 (technical documentation) and GDPR right-to-erasure
- **Nordic industrial SMEs**: target deployment environment in manufacturing
  and logistics (Centria's NextIndustriAI research program)
- **Quantum-secure communication**: BB84 QKD addresses the harvest-now-
  decrypt-later threat to FL systems before quantum computers mature

IBM Quantum Network membership would establish a formal research affiliation
with IBM, strengthen the PhD application, and provide the hardware validation
necessary to move from "working implementation" to "published result."

---

## Commitment

Upon receiving IBM Quantum Network access, I commit to:

1. Submit QFL paper to arXiv within 60 days
2. Acknowledge IBM Quantum Network in all publications
3. Present results at IBM Quantum Network events if invited
4. Open-source all hardware experiment code (already the project default)
5. Apply for IBM Quantum Research Award after paper acceptance

---

*Submitted: March 2026*
*Ali Pourrahim — Centria University of Applied Sciences*
