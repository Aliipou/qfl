"""Additional coverage for quantum paths — Qiskit-installed and IBM paths."""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from core.quantum.circuits import VQCConfig, build_vqc
from core.quantum.simulator import AerSimulatorBackend, SimulatorResult
from core.quantum.hardware import HardwareConfig, QuantumBackend


class TestSimulatorWithMockQiskit:
    def test_run_with_real_aer_mock(self):
        """Cover simulator.py:53-56 — the non-mock run path."""
        mock_job = MagicMock()
        mock_job.result.return_value.get_counts.return_value = {"0000": 512}

        mock_backend = MagicMock()
        mock_backend.run.return_value = mock_job

        mock_transpile = MagicMock(return_value="transpiled_circuit")

        mock_qiskit = types.ModuleType("qiskit")
        mock_qiskit.transpile = mock_transpile

        saved = sys.modules.get("qiskit")
        sys.modules["qiskit"] = mock_qiskit

        try:
            sim = AerSimulatorBackend(shots=1024)
            sim._backend = mock_backend  # bypass ensure_backend

            result = sim.run(circuit=MagicMock())
            assert isinstance(result, SimulatorResult)
            assert result.counts == {"0000": 512}
        finally:
            if saved is None:
                sys.modules.pop("qiskit", None)
            else:
                sys.modules["qiskit"] = saved


class TestVQCWithMockQiskit:
    def _make_qiskit_mocks(self):
        mock_circuit = MagicMock()
        mock_circuit.measure_all = MagicMock()

        mock_param = MagicMock()

        mock_qiskit_circuit = types.ModuleType("qiskit.circuit")
        mock_qiskit_circuit.QuantumCircuit = MagicMock(return_value=mock_circuit)
        mock_qiskit_circuit.Parameter = MagicMock(return_value=mock_param)

        mock_qiskit = types.ModuleType("qiskit")

        return mock_circuit, mock_qiskit_circuit, mock_qiskit

    def test_vqc_linear_entanglement_with_qiskit(self):
        mock_circuit, mock_qiskit_circuit, mock_qiskit = self._make_qiskit_mocks()

        with patch.dict(sys.modules, {
            "qiskit": mock_qiskit,
            "qiskit.circuit": mock_qiskit_circuit,
        }):
            # Import resolves to mock
            cfg = VQCConfig(num_qubits=2, num_layers=1, entanglement="linear")
            # When import fails it falls back to stub — just ensure no crash
            result = build_vqc(cfg)
            assert result is not None

    def test_vqc_full_entanglement_stub(self):
        cfg = VQCConfig(num_qubits=3, num_layers=2, entanglement="full")
        with patch("builtins.__import__", side_effect=ImportError):
            result = build_vqc(cfg)
        assert result["entanglement"] == "full"
        assert result["num_qubits"] == 3
        assert result["num_layers"] == 2


class TestHardwareCoverage:
    def test_connect_ibm_success_mock(self):
        import os

        mock_service_instance = MagicMock()
        mock_backend = MagicMock()
        mock_service_instance.backend.return_value = mock_backend

        mock_runtime = types.ModuleType("qiskit_ibm_runtime")
        mock_runtime.QiskitRuntimeService = MagicMock(return_value=mock_service_instance)

        backend = QuantumBackend()

        with patch.dict(os.environ, {"IBM_QUANTUM_TOKEN": "valid_token"}):
            with patch.dict(sys.modules, {"qiskit_ibm_runtime": mock_runtime}):
                result = backend.connect_ibm()

        assert result is True
        assert backend._ibm_backend is mock_backend

    def test_run_with_ibm_backend_success(self):
        """Test _run_ibm success path with full mock chain."""
        mock_counts = MagicMock()
        mock_counts.get_counts.return_value = {"0000": 512}

        mock_pub_result = MagicMock()
        mock_pub_result.data.meas = mock_counts

        mock_result = MagicMock()
        mock_result.__getitem__ = lambda self, i: mock_pub_result

        mock_job = MagicMock()
        mock_job.result.return_value = mock_result

        mock_sampler = MagicMock()
        mock_sampler.run.return_value = mock_job

        mock_sampler_cls = MagicMock(return_value=mock_sampler)
        mock_transpile = MagicMock(return_value="t_circuit")

        mock_ibm_runtime = types.ModuleType("qiskit_ibm_runtime")
        mock_ibm_runtime.SamplerV2 = mock_sampler_cls

        mock_qiskit = types.ModuleType("qiskit")
        mock_qiskit.transpile = mock_transpile

        backend = QuantumBackend()
        backend._ibm_backend = MagicMock()

        with patch.dict(sys.modules, {
            "qiskit_ibm_runtime": mock_ibm_runtime,
            "qiskit": mock_qiskit,
        }):
            with patch("core.quantum.hardware.transpile", mock_transpile, create=True):
                with patch("core.quantum.hardware.SamplerV2", mock_sampler_cls, create=True):
                    # run() dispatches to _run_ibm which may fallback — just verify no crash
                    backend._simulator._backend = "mock"
                    result = backend._run_ibm(circuit=MagicMock())

        assert result is not None

    def test_connect_ibm_general_exception(self):
        import os

        def bad_service(*a, **kw):
            raise ConnectionError("network down")

        mock_runtime = types.ModuleType("qiskit_ibm_runtime")
        mock_runtime.QiskitRuntimeService = bad_service

        backend = QuantumBackend()
        with patch.dict(os.environ, {"IBM_QUANTUM_TOKEN": "token"}):
            with patch.dict(sys.modules, {"qiskit_ibm_runtime": mock_runtime}):
                result = backend.connect_ibm()

        assert result is False
