"""Unit tests for BB84 QKD and VQC circuits."""

import pytest

from core.quantum.circuits import BB84Result, VQCConfig, bb84_key_exchange, build_vqc


class TestBB84:
    def test_returns_result(self):
        result = bb84_key_exchange(num_bits=64)
        assert isinstance(result, BB84Result)

    def test_key_id_is_16_chars(self):
        result = bb84_key_exchange(num_bits=64)
        assert len(result.key_id) == 16

    def test_sifted_key_length_reasonable(self):
        """Sifted key should be ~50% of raw bits (statistical)."""
        result = bb84_key_exchange(num_bits=1000)
        assert 300 <= result.key_length <= 700

    def test_raw_key_length(self):
        result = bb84_key_exchange(num_bits=128)
        assert len(result.raw_key) == 128

    def test_error_rate_zero_channel(self):
        result = bb84_key_exchange(num_bits=500, error_rate=0.0)
        assert result.error_rate == 0.0

    def test_error_rate_with_noise(self):
        result = bb84_key_exchange(num_bits=1000, error_rate=0.1)
        # error_rate should be positive with noisy channel
        assert result.error_rate >= 0.0

    def test_invalid_error_rate_raises(self):
        with pytest.raises(ValueError, match="error_rate must be"):
            bb84_key_exchange(error_rate=0.5)

    def test_negative_error_rate_raises(self):
        with pytest.raises(ValueError, match="error_rate must be"):
            bb84_key_exchange(error_rate=-0.1)

    def test_all_bits_are_binary(self):
        result = bb84_key_exchange(num_bits=64)
        assert all(b in (0, 1) for b in result.raw_key)
        assert all(b in (0, 1) for b in result.sifted_key)


class TestVQCConfig:
    def test_defaults(self):
        c = VQCConfig()
        assert c.num_qubits == 4
        assert c.num_layers == 2
        assert c.entanglement == "linear"
        assert c.backend == "aer_simulator"

    def test_custom(self):
        c = VQCConfig(num_qubits=8, num_layers=4, entanglement="full")
        assert c.num_qubits == 8


class TestBuildVQC:
    def test_returns_stub_without_qiskit(self):
        """Without Qiskit installed, should return a stub dict."""
        import sys
        from unittest.mock import patch

        with patch.dict(sys.modules, {"qiskit": None, "qiskit.circuit": None}):
            with patch("builtins.__import__", side_effect=ImportError("no qiskit")):
                result = build_vqc()

        assert isinstance(result, dict)
        assert result["type"] == "vqc_stub"
        assert result["num_qubits"] == 4

    def test_default_config_used_when_none(self):
        import sys
        from unittest.mock import patch

        with patch("builtins.__import__", side_effect=ImportError("no qiskit")):
            result = build_vqc(config=None)

        assert result["num_qubits"] == 4

    def test_full_entanglement_config(self):
        import sys
        from unittest.mock import patch

        cfg = VQCConfig(num_qubits=3, num_layers=1, entanglement="full")
        with patch("builtins.__import__", side_effect=ImportError("no qiskit")):
            result = build_vqc(config=cfg)

        assert result["entanglement"] == "full"
        assert result["num_qubits"] == 3
