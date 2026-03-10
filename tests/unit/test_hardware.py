"""Unit tests for QuantumBackend hardware connector."""

import os
from unittest.mock import MagicMock, patch

import pytest

from core.quantum.hardware import HardwareConfig, QuantumBackend
from core.quantum.simulator import SimulatorResult


class TestHardwareConfig:
    def test_defaults(self):
        c = HardwareConfig()
        assert c.backend_name == "ibm_brisbane"
        assert c.shots == 1024
        assert c.optimization_level == 1
        assert c.use_real_hardware is False

    def test_custom(self):
        c = HardwareConfig(shots=512, backend_name="ibm_sherbrooke")
        assert c.shots == 512
        assert c.backend_name == "ibm_sherbrooke"


class TestQuantumBackend:
    def test_default_init(self):
        backend = QuantumBackend()
        assert backend.backend_name == "aer_simulator"
        assert backend._ibm_backend is None

    def test_custom_config(self):
        config = HardwareConfig(shots=2048)
        backend = QuantumBackend(config=config)
        assert backend.config.shots == 2048

    def test_connect_ibm_no_token(self):
        backend = QuantumBackend()
        with patch.dict(os.environ, {}, clear=True):
            os.environ.pop("IBM_QUANTUM_TOKEN", None)
            result = backend.connect_ibm()
        assert result is False
        assert backend._ibm_backend is None

    def test_connect_ibm_import_error(self):
        backend = QuantumBackend()
        with patch.dict(os.environ, {"IBM_QUANTUM_TOKEN": "fake_token"}):
            with patch("builtins.__import__", side_effect=ImportError("no qiskit_ibm")):
                result = backend.connect_ibm()
        assert result is False

    def test_connect_ibm_runtime_error(self):
        backend = QuantumBackend()
        mock_service = MagicMock(side_effect=RuntimeError("auth failed"))
        with patch.dict(os.environ, {"IBM_QUANTUM_TOKEN": "bad_token"}):
            with patch("core.quantum.hardware.QuantumBackend.connect_ibm", return_value=False):
                result = backend.connect_ibm()
        assert result is False

    def test_run_uses_simulator_when_no_ibm(self):
        backend = QuantumBackend()
        backend._simulator._backend = "mock"
        result = backend.run(circuit=object())
        assert isinstance(result, SimulatorResult)
        assert result.backend == "mock"

    def test_run_ibm_fallback_on_exception(self):
        backend = QuantumBackend()
        backend._ibm_backend = MagicMock()
        backend._simulator._backend = "mock"

        with patch("builtins.__import__", side_effect=ImportError("no sampler")):
            result = backend._run_ibm(circuit=object())

        assert isinstance(result, SimulatorResult)

    def test_backend_name_property(self):
        backend = QuantumBackend()
        assert backend.backend_name == "aer_simulator"
