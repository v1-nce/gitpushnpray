from __future__ import annotations

import unittest

from scripts.benchmark_runtime import _memory_counters, _percentile


class BenchmarkRuntimeTest(unittest.TestCase):
    def test_percentile_uses_nearest_rank_without_interpolation(self) -> None:
        ordered = [float(value) for value in range(1, 101)]
        self.assertEqual(_percentile(ordered, 0.50), 50.0)
        self.assertEqual(_percentile(ordered, 0.95), 95.0)
        self.assertEqual(_percentile(ordered, 0.99), 99.0)

    def test_percentile_clamps_to_the_observed_range(self) -> None:
        self.assertEqual(_percentile([], 0.95), 0.0)
        self.assertEqual(_percentile([7.0], 0.01), 7.0)
        self.assertEqual(_percentile([1.0, 2.0, 3.0], 1.0), 3.0)

    def test_memory_probe_reports_a_positive_working_set(self) -> None:
        counters = _memory_counters()
        if counters is None:
            self.skipTest("no supported memory probe on this platform")
        current, peak = counters
        self.assertGreater(current, 0)
        self.assertGreaterEqual(peak, current)


if __name__ == "__main__":
    unittest.main()
