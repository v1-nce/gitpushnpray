from __future__ import annotations

import unittest

from scripts.shadow_evaluator import paraphrase_constraint, scenario_sequence


class ShadowEvaluatorTest(unittest.TestCase):
    def test_scenario_sequence_has_official_mix_per_twenty_samples(self) -> None:
        scenarios = scenario_sequence(200, seed=42)
        self.assertEqual(scenarios.count("buying"), 80)
        self.assertEqual(scenarios.count("browsing"), 80)
        self.assertEqual(scenarios.count("intent_override"), 30)
        self.assertEqual(scenarios.count("boundary"), 10)

    def test_constraint_paraphrases_are_deterministic(self) -> None:
        self.assertEqual(paraphrase_constraint("color: Blue"), "the Blue color")
        self.assertEqual(paraphrase_constraint("cotton"), "made from cotton")
        self.assertEqual(paraphrase_constraint("budget around $35"), "priced at about $35")


if __name__ == "__main__":
    unittest.main()
