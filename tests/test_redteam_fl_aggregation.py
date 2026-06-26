"""Aggressive red-team of qfl's federated aggregation (core.federated.aggregation).

Finding: plain FedAvg has NO Byzantine robustness and NO input validation. These
tests mount real federated-learning attacks and PIN the current (vulnerable)
behaviour as documented limitations of a research-tier aggregator. If any
`test_VULN_*` starts failing, a defense was added — update THREAT_MODEL.

The fix is robust aggregation (coordinate-wise median / trimmed mean / Krum) plus
per-client norm clipping and input sanitization — future work, not implemented here.
"""

import math
import unittest

import numpy as np

from core.federated.aggregation import fed_avg


class TestHonestBaseline(unittest.TestCase):
    def test_weighted_mean_is_correct(self):
        agg = fed_avg([[np.array([0.0, 0.0])], [np.array([10.0, 10.0])]], [1, 3])
        np.testing.assert_allclose(agg[0], [7.5, 7.5])  # (0*1 + 10*3) / 4

    def test_zero_total_samples_raises(self):
        # the one validation that does exist
        with self.assertRaises(ValueError):
            fed_avg([[np.ones(2)]], [0])


class TestAttacks(unittest.TestCase):
    def test_VULN_single_poisoned_client_dominates(self):
        # 4 honest clients (weights ~1) + 1 attacker with enormous weights.
        clients = [[np.ones(2)] for _ in range(4)] + [[np.full(2, 1e6)]]
        agg = fed_avg(clients, [100] * 5)
        # honest mean would be ~1; the attacker drags it into the thousands.
        self.assertGreater(float(agg[0][0]), 1000.0,
                           "VULN closed? model poisoning no longer dominates")

    def test_VULN_sample_count_inflation_seizes_control(self):
        # attacker lies about local sample count to grab the aggregation weight.
        agg = fed_avg([[np.zeros(2)], [np.full(2, 5.0)]], [100, 10**9])
        self.assertAlmostEqual(float(agg[0][0]), 5.0, delta=0.01,
                               msg="VULN closed? sample-count inflation no longer controls")

    def test_VULN_nan_injection_corrupts_global_model(self):
        agg = fed_avg([[np.ones(2)], [np.full(2, np.nan)]], [100, 100])
        self.assertTrue(math.isnan(float(agg[0][0])),
                        "VULN closed? NaN updates no longer corrupt the aggregate")

    def test_VULN_inf_injection_corrupts_global_model(self):
        agg = fed_avg([[np.ones(2)], [np.full(2, np.inf)]], [100, 100])
        self.assertTrue(math.isinf(float(agg[0][0])),
                        "VULN closed? Inf updates no longer corrupt the aggregate")


if __name__ == "__main__":
    unittest.main()
