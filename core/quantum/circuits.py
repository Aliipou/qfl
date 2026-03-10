"""QKD (BB84) and VQC circuit implementations (Phase 2 scaffold)."""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# BB84 QKD Simulation
# ---------------------------------------------------------------------------

@dataclass
class BB84Result:
    raw_key: list[int]
    sifted_key: list[int]
    key_length: int
    error_rate: float
    key_id: str


def bb84_key_exchange(num_bits: int = 256, error_rate: float = 0.0) -> BB84Result:
    """
    Simulate BB84 QKD protocol key exchange.

    Args:
        num_bits: Number of raw bits to generate.
        error_rate: Simulated channel error rate (0.0–0.25 safe range).

    Returns:
        BB84Result with sifted key usable for symmetric encryption.
    """
    if not 0.0 <= error_rate < 0.5:
        raise ValueError(f"error_rate must be in [0, 0.5), got {error_rate}")

    # Alice generates random bits + bases
    alice_bits = [random.randint(0, 1) for _ in range(num_bits)]
    alice_bases = [random.randint(0, 1) for _ in range(num_bits)]  # 0=+, 1=×

    # Bob chooses random measurement bases
    bob_bases = [random.randint(0, 1) for _ in range(num_bits)]

    # Simulate measurement (with optional channel errors)
    bob_bits = []
    for a_bit, a_base, b_base in zip(alice_bits, alice_bases, bob_bases):
        if a_base == b_base:
            # Correct basis → correct measurement (maybe with error)
            bit = 1 - a_bit if random.random() < error_rate else a_bit
        else:
            # Wrong basis → random result
            bit = random.randint(0, 1)
        bob_bits.append(bit)

    # Sifting: keep only bits where bases matched
    sifted_key = [
        alice_bits[i]
        for i in range(num_bits)
        if alice_bases[i] == bob_bases[i]
    ]

    import hashlib, secrets
    key_id = hashlib.sha256(secrets.token_bytes(16)).hexdigest()[:16]

    actual_error = sum(
        alice_bits[i] != bob_bits[i]
        for i in range(num_bits)
        if alice_bases[i] == bob_bases[i]
    ) / max(len(sifted_key), 1)

    logger.info(
        "BB84: raw=%d bits, sifted=%d bits, error_rate=%.3f, key_id=%s",
        num_bits,
        len(sifted_key),
        actual_error,
        key_id,
    )

    return BB84Result(
        raw_key=alice_bits,
        sifted_key=sifted_key,
        key_length=len(sifted_key),
        error_rate=actual_error,
        key_id=key_id,
    )


# ---------------------------------------------------------------------------
# VQC — Variational Quantum Circuit (Phase 2 scaffold)
# ---------------------------------------------------------------------------

@dataclass
class VQCConfig:
    num_qubits: int = 4
    num_layers: int = 2
    entanglement: str = "linear"  # "linear" | "full"
    backend: str = "aer_simulator"


def build_vqc(config: VQCConfig | None = None) -> object:
    """
    Build a parameterized VQC with RY/RZ gates and entanglement.

    Returns a Qiskit QuantumCircuit if Qiskit is installed,
    or a stub dict for Phase 1 testing.
    """
    if config is None:
        config = VQCConfig()

    try:
        from qiskit.circuit import Parameter, QuantumCircuit  # type: ignore[import]

        qc = QuantumCircuit(config.num_qubits)
        params = []

        for layer in range(config.num_layers):
            for q in range(config.num_qubits):
                ry = Parameter(f"θ_ry_{layer}_{q}")
                rz = Parameter(f"θ_rz_{layer}_{q}")
                params.extend([ry, rz])
                qc.ry(ry, q)
                qc.rz(rz, q)

            # Entanglement
            if config.entanglement == "linear":
                for q in range(config.num_qubits - 1):
                    qc.cx(q, q + 1)
            elif config.entanglement == "full":
                for q in range(config.num_qubits):
                    for q2 in range(q + 1, config.num_qubits):
                        qc.cx(q, q2)

        qc.measure_all()
        logger.info("VQC built: %d qubits, %d layers", config.num_qubits, config.num_layers)
        return qc

    except ImportError:
        logger.warning("Qiskit not installed — returning VQC stub")
        return {
            "type": "vqc_stub",
            "num_qubits": config.num_qubits,
            "num_layers": config.num_layers,
            "entanglement": config.entanglement,
        }
