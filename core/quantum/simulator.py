"""Local Aer simulator fallback — used when IBM Quantum is unavailable."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

BACKEND_NAME = "aer_simulator"


@dataclass
class SimulatorResult:
    counts: dict[str, int]
    shots: int
    backend: str = BACKEND_NAME
    metadata: dict = field(default_factory=dict)

    @property
    def most_frequent(self) -> str:
        return max(self.counts, key=lambda k: self.counts[k])


class AerSimulatorBackend:
    """
    Thin wrapper around Qiskit Aer for Phase 1–2.

    Defers importing Qiskit so the API boots without quantum deps installed.
    """

    def __init__(self, shots: int = 1024) -> None:
        self.shots = shots
        self._backend = None

    def _ensure_backend(self) -> None:
        if self._backend is None:
            try:
                from qiskit_aer import AerSimulator  # type: ignore[import]
                self._backend = AerSimulator()
                logger.info("Aer simulator initialised")
            except ImportError:
                logger.warning("qiskit-aer not installed — using mock backend")
                self._backend = "mock"

    def run(self, circuit: object) -> SimulatorResult:
        self._ensure_backend()
        if self._backend == "mock":
            return self._mock_run()

        from qiskit import transpile  # type: ignore[import]

        transpiled = transpile(circuit, self._backend)
        job = self._backend.run(transpiled, shots=self.shots)
        counts = job.result().get_counts()
        return SimulatorResult(counts=counts, shots=self.shots)

    def _mock_run(self) -> SimulatorResult:
        """Returns a deterministic mock result for unit testing."""
        return SimulatorResult(
            counts={"0" * 4: self.shots},
            shots=self.shots,
            backend="mock",
        )
