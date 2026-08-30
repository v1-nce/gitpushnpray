from __future__ import annotations

import unittest

import statistics

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


    def test_popularity_matching_tracks_the_reference_profile(self) -> None:
        """Uniform sampling draws the catalog's long tail, which the official
        targets are not: real purchase records skew heavily popular, and a ranking
        signal correlated with popularity is misjudged against the wrong pool."""
        products = {
            f"B{index:04d}": {
                "categories": ["Clothing", "Shirts"],
                "title": f"shirt {index}",
                # A long tail: most products have almost no reviews.
                "rating_number": 20000 if index % 25 == 0 else index % 8,
            }
            for index in range(500)
        }
        reference = [20000] * 40  # the official profile: popular products only

        matched, _ = select_targets(
            products, set(), 15, seed=3, require_two_constraints=False,
            reference_counts=reference,
        )
        uniform, _ = select_targets(
            products, set(), 15, seed=3, require_two_constraints=False,
        )

        def median_reviews(ids: list[str]) -> float:
            return statistics.median(products[i]["rating_number"] for i in ids)

        self.assertGreater(median_reviews(matched), median_reviews(uniform))
        self.assertEqual(len(matched), 15)
        self.assertEqual(len(set(matched)), 15)

    def test_popularity_matching_is_deterministic(self) -> None:
        products = {
            f"B{index:04d}": {
                "categories": ["Clothing"],
                "title": f"item {index}",
                "rating_number": index * 7,
            }
            for index in range(200)
        }
        reference = [500, 40, 900, 12, 300] * 4
        first, _ = select_targets(
            products, set(), 10, seed=11, require_two_constraints=False,
            reference_counts=reference,
        )
        second, _ = select_targets(
            products, set(), 10, seed=11, require_two_constraints=False,
            reference_counts=reference,
        )
        self.assertEqual(first, second)


if __name__ == "__main__":
    unittest.main()
