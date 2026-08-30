from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from starter.agent import Agent


class AgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        catalog_path = Path(self.temporary_directory.name) / "catalog.jsonl"
        products = [
            {
                "parent_asin": "TARGET",
                "title": "Trail Runner Pro",
                "features": ["waterproof membrane", "wide toe box"],
                "details": {"Department": "Womens"},
                "description": ["blue hiking and running shoe"],
                "price": 79.0,
                "categories": ["Clothing, Shoes & Jewelry", "Women", "Shoes", "Trail Running"],
                "average_rating": 4.5,
                "rating_number": 100,
                "store": "Example",
            },
            {
                "parent_asin": "OTHER",
                "title": "Everyday Runner",
                "features": ["breathable mesh"],
                "details": {"Department": "Womens"},
                "description": ["casual walking shoe"],
                "price": 49.0,
                "categories": ["Clothing, Shoes & Jewelry", "Women", "Shoes", "Trail Running"],
                "average_rating": 4.8,
                "rating_number": 500,
                "store": "Example",
            },
        ]
        catalog_path.write_text(
            "".join(json.dumps(product) + "\n" for product in products),
            encoding="utf-8",
        )
        self.agent = Agent(catalog_path)
        self.profile = {
            "preference_tags": ["comfort"],
            "summary": "Prior purchases emphasize comfort.",
        }

    def tearDown(self) -> None:
        self.agent.connection.close()
        self.temporary_directory.cleanup()

    def test_accumulated_exact_evidence_ranks_matching_product_first(self) -> None:
        self.agent.reset("session", self.profile)
        self.agent.respond("session", "I'm looking for Shoes Trail Running, but I'm still exploring.", 1, 10)
        response = self.agent.respond(
            "session",
            "For that, what matters is: waterproof membrane.",
            2,
            10,
        )
        self.assertEqual(response["recommendations"][0]["parent_asin"], "TARGET")
        self.assertEqual(self.agent._sessions["session"].category, "Shoes Trail Running")

    def test_boundary_decline_switches_from_other_to_typed_question(self) -> None:
        self.agent.reset("session", self.profile)
        first = self.agent.respond(
            "session", "I'm looking for Shoes Trail Running, but I'm still exploring.", 1, 10
        )
        second = self.agent.respond(
            "session",
            "I don't have a preference for other; please use your judgment.",
            2,
            10,
        )
        self.assertEqual(first["ask_attribute"], "other")
        self.assertIn(
            second["ask_attribute"],
            ("feature", "material", "color", "style", "use_case", "size", "budget", "brand"),
        )

    def test_override_demotes_superseded_preference_to_soft(self) -> None:
        self.agent.reset("session", self.profile)
        self.agent.respond(
            "session", "I'm looking for Shoes Trail Running. waterproof membrane.", 1, 10
        )
        self.agent.respond(
            "session",
            "Actually, ignore my earlier preference. What I need is: wide toe box.",
            3,
            10,
        )
        state = self.agent._sessions["session"]
        self.assertEqual([constraint.normalized for constraint in state.hard], ["wide toe box"])
        self.assertEqual([constraint.normalized for constraint in state.soft], ["waterproof membrane"])

    def test_explicit_retraction_erases_superseded_constraint(self) -> None:
        self.agent.reset("session", self.profile)
        self.agent.respond(
            "session", "I need Shoes Trail Running. breathable mesh.", 1, 10
        )
        self.agent.respond(
            "session",
            "Scratch that earlier requirement; I no longer want it. Instead I need: wide toe box.",
            3,
            10,
        )
        state = self.agent._sessions["session"]
        self.assertEqual([constraint.normalized for constraint in state.hard], ["wide toe box"])
        self.assertEqual(state.soft, [])

    def test_paraphrased_category_and_requirement_are_understood(self) -> None:
        self.agent.reset("session", self.profile)
        response = self.agent.respond(
            "session",
            "Please help me find some Shoes Trail Running. It must have a waterproof membrane.",
            1,
            10,
        )
        state = self.agent._sessions["session"]
        self.assertEqual(state.category, "Shoes Trail Running")
        self.assertEqual([constraint.normalized for constraint in state.hard], ["a waterproof membrane"])
        self.assertEqual(response["recommendations"][0]["parent_asin"], "TARGET")

    def test_paraphrased_browsing_message_does_not_become_constraint(self) -> None:
        self.agent.reset("session", self.profile)
        self.agent.respond(
            "session", "Could you show me some Shoes Trail Running? I'm open to ideas.", 1, 10
        )
        state = self.agent._sessions["session"]
        self.assertEqual(state.category, "Shoes Trail Running")
        self.assertEqual(state.hard, [])

    def test_paraphrased_no_preference_retires_attribute(self) -> None:
        self.agent.reset("session", self.profile)
        self.agent.respond(
            "session", "I have no preference about color; choose what works.", 2, 10
        )
        self.assertIn("color", self.agent._sessions["session"].no_preference_attributes)

    def test_reset_keeps_session_state_isolated(self) -> None:
        self.agent.reset("one", self.profile)
        self.agent.reset("two", self.profile)
        self.agent.respond("one", "I'm looking for Shoes Trail Running. A key requirement is: waterproof membrane.", 1, 10)
        self.assertEqual(self.agent._sessions["two"].hard, [])
        self.assertEqual(self.agent._sessions["two"].soft, [])

    def test_typed_question_can_repeat_after_user_supplies_evidence(self) -> None:
        self.agent.reset("session", self.profile)
        self.agent.respond(
            "session", "I'm looking for Shoes Trail Running, but I'm still exploring.", 1, 10
        )
        self.agent.respond(
            "session",
            "I don't have a preference for other; please use your judgment.",
            2,
            10,
        )
        response = self.agent.respond(
            "session",
            "For that, what matters is: waterproof membrane.",
            3,
            10,
        )
        self.assertEqual(response["ask_attribute"], "feature")

    def test_reworded_category_and_marker_extract_evidence(self) -> None:
        self.agent.reset("session", self.profile)
        response = self.agent.respond(
            "session",
            "I need a Shoes Trail Running. The thing that matters most is: waterproof membrane.",
            1,
            10,
        )
        state = self.agent._sessions["session"]
        self.assertEqual(state.category, "Shoes Trail Running")
        self.assertEqual([c.normalized for c in state.hard], ["waterproof membrane"])
        self.assertEqual(response["recommendations"][0]["parent_asin"], "TARGET")

    def test_synonym_overlap_recovers_water_resistant(self) -> None:
        self.agent.reset("session", self.profile)
        self.agent.respond("session", "I'm looking for Shoes Trail Running.", 1, 10)
        response = self.agent.respond(
            "session",
            "For that, what matters is: water-resistant membrane.",
            2,
            10,
        )
        self.assertEqual(response["recommendations"][0]["parent_asin"], "TARGET")

    def test_reworded_override_demotes_and_replaces(self) -> None:
        self.agent.reset("session", self.profile)
        self.agent.respond(
            "session", "I want a Shoes Trail Running. waterproof membrane.", 1, 10
        )
        self.agent.respond(
            "session", "Actually, ignore my earlier preference. Instead, wide toe box.", 2, 10
        )
        state = self.agent._sessions["session"]
        self.assertEqual([c.normalized for c in state.hard], ["wide toe box"])
        self.assertEqual([c.normalized for c in state.soft], ["waterproof membrane"])

    def test_exploratory_rest_is_not_a_constraint(self) -> None:
        self.agent.reset("session", self.profile)
        self.agent.respond(
            "session", "I'm looking for Shoes Trail Running, but I'm still exploring.", 1, 10
        )
        state = self.agent._sessions["session"]
        self.assertEqual(state.category, "Shoes Trail Running")
        self.assertEqual(state.hard, [])
        self.assertEqual(state.soft, [])


if __name__ == "__main__":
    unittest.main()
