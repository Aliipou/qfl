"""IBM Quantum / IonQ hardware connector with Aer fallback."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any

from core.quantum.simulator import AerSimulatorBackend, SimulatorResult

logger = logging.getLogger(__name__)

IBM_TOKEN_ENV = "IBM_QUANTUM_TOKEN"
IBM_CHANNEL = "ibm_quantum"


@dataclass
class HardwareConfig:
    backend_name: str = "ibm_brisbane"
    shots: int = 1024
    optimization_level: int = 1
    use_real_hardware: bool = False


class QuantumBackend:
    """
    Unified quantum backend: real IBM Quantum hardware or local Aer fallback.

    Lazy-loads IBM Runtime to allow the service to boot without credentials.
    """

    def __init__(self, config: HardwareConfig | None = None) -> None:
        self.config = config or HardwareConfig()
        self._simulator = AerSimulatorBackend(shots=self.config.shots)
        self._ibm_backend: Any = None
        self._active_backend = "aer_simulator"

    def connect_ibm(self) -> bool:
        """Attempt to connect to IBM Quantum. Returns True on success."""
        token = os.getenv(IBM_TOKEN_ENV)
        if not token:
            logger.warning("IBM_QUANTUM_TOKEN not set — using Aer simulator")
            return False

        try:
            from qiskit_ibm_runtime import QiskitRuntimeService  # type: ignore[import]

            service = QiskitRuntimeService(channel=IBM_CHANNEL, token=token)
            self._ibm_backend = service.backend(self.config.backend_name)
            self._active_backend = self.config.backend_name
            logger.info("Connected to IBM Quantum backend: %s", self.config.backend_name)
            return True
        except ImportError:
            logger.warning("qiskit-ibm-runtime not installed — using Aer")
            return False
        except Exception as exc:
            logger.error("IBM Quantum connection failed: %s", exc)
            return False

    @property
    def backend_name(self) -> str:
        return self._active_backend

    def run(self, circuit: Any) -> SimulatorResult:
        """Run a circuit on the active backend (hardware or simulator)."""
        if self._ibm_backend is not None:
            return self._run_ibm(circuit)
        return self._simulator.run(circuit)

    def _run_ibm(self, circuit: Any) -> SimulatorResult:
        try:
            from qiskit_ibm_runtime import SamplerV2 as Sampler  # type: ignore[import]
            from qiskit import transpile  # type: ignore[import]

            transpiled = transpile(circuit, self._ibm_backend)
            sampler = Sampler(backend=self._ibm_backend)
            job = sampler.run([transpiled], shots=self.config.shots)
            result = job.result()
            counts = result[0].data.meas.get_counts()
            return SimulatorResult(
                counts=counts,
                shots=self.config.shots,
                backend=self._active_backend,
            )
        except Exception as exc:
            logger.error("IBM run failed, falling back to Aer: %s", exc)
            return self._simulator.run(circuit)
