from __future__ import annotations

import unittest

from scripts.unseen_target_evaluator import build_samples, scenario_sequence, select_targets


class UnseenTargetEvaluatorTest(unittest.TestCase):
    def test_scenario_sequence_keeps_the_official_mix(self) -> None:
        scenarios = scenario_sequence(200, seed=20260830)
        self.assertEqual(scenarios.count("buying"), 80)
        self.assertEqual(scenarios.count("browsing"), 80)
        self.assertEqual(scenarios.count("intent_override"), 30)
        self.assertEqual(scenarios.count("boundary"), 10)

    def test_selection_excludes_public_targets_and_is_deterministic(self) -> None:
        products = {
            f"B{index:04d}": {"categories": ["Clothing", "Shirts"], "title": f"shirt {index}"}
            for index in range(50)
        }
        excluded = {"B0000", "B0001", "B0002"}
        first, _ = select_targets(products, excluded, 10, seed=7, require_two_constraints=False)
        second, _ = select_targets(products, excluded, 10, seed=7, require_two_constraints=False)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 10)
        self.assertFalse(excluded.intersection(first))

    def test_samples_match_the_official_session_shape(self) -> None:
        samples = build_samples(["B1", "B2"], ["buying", "boundary"])
        self.assertEqual(samples[0]["ground_truth"]["parent_asin"], "B1")
        self.assertEqual(samples[1]["scenario_type"], "boundary")
        for sample in samples:
            self.assertLessEqual(
                {"sample_id", "scenario_type", "user_profile", "ground_truth"},
                set(sample),
            )


if __name__ == "__main__":
    unittest.main()
