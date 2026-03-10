"""Unit tests for AerSimulatorBackend."""

from unittest.mock import MagicMock, patch

import pytest

from core.quantum.simulator import AerSimulatorBackend, SimulatorResult


class TestSimulatorResult:
    def test_most_frequent(self):
        r = SimulatorResult(counts={"0000": 900, "0001": 100}, shots=1000)
        assert r.most_frequent == "0000"

    def test_backend_default(self):
        r = SimulatorResult(counts={"0000": 1024}, shots=1024)
        assert r.backend == "aer_simulator"


class TestAerSimulatorBackend:
    def test_mock_run_when_qiskit_missing(self):
        backend = AerSimulatorBackend(shots=512)
        with patch.dict("sys.modules", {"qiskit_aer": None}):
            backend._backend = None
            with patch("builtins.__import__", side_effect=ImportError):
                # Force mock path
                backend._backend = "mock"
                result = backend._mock_run()
        assert result.shots == 512
        assert result.backend == "mock"
        assert "0000" in result.counts

    def test_mock_run_returns_all_zeros(self):
        backend = AerSimulatorBackend(shots=256)
        result = backend._mock_run()
        assert result.counts == {"0000": 256}
        assert result.most_frequent == "0000"

    def test_ensure_backend_sets_mock_on_import_error(self):
        backend = AerSimulatorBackend()
        with patch("builtins.__import__", side_effect=ImportError("no qiskit")):
            backend._ensure_backend()
        assert backend._backend == "mock"

    def test_run_uses_mock_backend(self):
        backend = AerSimulatorBackend(shots=128)
        backend._backend = "mock"
        result = backend.run(circuit=object())
        assert isinstance(result, SimulatorResult)
        assert result.shots == 128

    def test_ensure_backend_idempotent(self):
        backend = AerSimulatorBackend()
        backend._backend = "mock"
        backend._ensure_backend()  # Should not reset
        assert backend._backend == "mock"
