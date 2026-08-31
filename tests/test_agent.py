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


    def test_embedded_catalog_phrase_resolves_through_conversational_wrapping(self) -> None:
        """A requirement wrapped in the customer's own words still matches exactly."""
        bare = self.agent._exact_lookup("waterproof membrane", None)
        self.assertIn("TARGET", bare)
        # Whole-payload equality fails once the customer wraps the phrase.
        self.assertEqual(self.agent._exact_lookup("i would like waterproof membrane", None), set())
        # The embedded phrase is still recovered.
        embedded = self.agent._embedded_phrase_matches("i would like waterproof membrane", None)
        self.assertIn("TARGET", embedded)

    def test_embedded_phrase_search_ignores_single_token_payloads(self) -> None:
        self.assertEqual(self.agent._embedded_phrase_matches("waterproof", None), set())

    def test_embedded_phrase_never_reduces_typed_recall(self) -> None:
        """Merging the two routes may add candidates but must never drop one."""
        from starter.agent import Constraint

        constraint = Constraint(
            value="I would like waterproof membrane",
            normalized="i would like waterproof membrane",
            kind="hard",
            attribute="feature",
        )
        resolved = dict(self.agent._resolve_constraint(constraint, None))
        typed = self.agent._typed_matches(constraint, None)
        self.assertLessEqual(set(typed), set(resolved))
        # The embedded match is recorded at the stronger rung.
        self.assertEqual(resolved.get("TARGET"), 1)

    def test_emit_fills_full_ranking_only_once_no_question_remains(self) -> None:
        """A pending question keeps the conservative tier slice; exhaustion fills."""
        from starter.agent import Constraint, SessionState

        state = SessionState(
            profile_terms=[],
            hard=[
                Constraint(
                    value="cotton",
                    normalized="cotton",
                    kind="hard",
                    attribute="material",
                )
            ],
        )
        ranked = ["TARGET", "OTHER"]
        coverage = {"TARGET": (1, 0, 2), "OTHER": (0, 0, 0)}
        # While a clarification is pending, only the single top coverage tier is
        # endorsed so an early wide list cannot trade MRR for efficiency.
        self.assertEqual(
            self.agent._emit(ranked, coverage, 10, state, pending_question=True),
            ["TARGET"],
        )
        # Once no productive question remains, fill from the full ranking.
        self.assertEqual(
            self.agent._emit(ranked, coverage, 10, state, pending_question=False),
            ["TARGET", "OTHER"],
        )

    def test_index_cache_round_trip_reproduces_runtime_dicts(self) -> None:
        """A warm start restores the same quality and searchable dictionaries."""
        index_path = Path(self.temporary_directory.name) / "cache.index.db"
        first = Agent(self.agent.catalog_path, index_path=index_path)
        expected_quality = dict(first._quality)
        expected_searchable = dict(first._searchable)
        first.connection.close()
        second = Agent(self.agent.catalog_path, index_path=index_path)
        try:
            self.assertEqual(second._quality, expected_quality)
            self.assertEqual(second._searchable, expected_searchable)
        finally:
            second.connection.close()


if __name__ == "__main__":
    unittest.main()
