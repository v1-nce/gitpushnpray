from __future__ import annotations

import argparse
import json
import math
import random
import re
import statistics
from collections import defaultdict
from pathlib import Path

from evaluator.local_evaluator import (
    MAX_TURNS,
    TOP_K,
    classify_constraint,
    coarse_category,
    intent_card,
    load_jsonl,
    normalize_recommendations,
)
from starter.agent import Agent


SCENARIO_BLOCK = (
    *("buying",) * 8,
    *("browsing",) * 8,
    *("intent_override",) * 3,
    "boundary",
)


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def paraphrase_constraint(value: str) -> str:
    """Apply deterministic surface changes without inventing product facts."""
    cleaned = re.sub(r"\s+", " ", value).strip(" .")
    budget = re.fullmatch(r"budget around \$?([0-9]+(?:\.[0-9]+)?)", cleaned, re.I)
    if budget:
        return f"priced at about ${budget.group(1)}"
    color = re.fullmatch(r"color:\s*(.+)", cleaned, re.I)
    if color:
        return f"the {color.group(1)} color"
    key_value = re.fullmatch(r"([^:]{2,40}):\s*(.+)", cleaned)
    if key_value:
        return f"{key_value.group(2)} for {key_value.group(1).lower()}"
    if len(cleaned.split()) == 1:
        return f"made from {cleaned}"
    return f"I would like {cleaned}"


def scenario_sequence(sample_count: int, seed: int) -> list[str]:
    scenarios = [SCENARIO_BLOCK[index % len(SCENARIO_BLOCK)] for index in range(sample_count)]
    random.Random(seed ^ 0x5EED).shuffle(scenarios)
    return scenarios


def _popularity_bucket(review_count: int) -> int:
    """Coarse log2 band of a product's review count."""
    return int(math.log2(review_count)) if review_count > 0 else -1


def select_targets(
    products: dict[str, dict],
    excluded_ids: set[str],
    sample_count: int,
    seed: int,
    reference_counts: list[int] | None = None,
) -> list[dict]:
    candidates = []
    for parent_asin, product in products.items():
        if parent_asin in excluded_ids:
            continue
        card = intent_card(product)
        if len(card.get("hard_constraints", [])) < 2:
            continue
        if not product.get("categories"):
            continue
        candidates.append(product)
    if len(candidates) < sample_count:
        raise ValueError(f"requested {sample_count} targets but only {len(candidates)} qualify")

    rng = random.Random(seed)
    if not reference_counts:
        rng.shuffle(candidates)
        return candidates[:sample_count]

    # Official targets are real purchase records and skew heavily popular, with a
    # median review count around 7000 against 12 for the catalog. Sampling the
    # catalog uniformly builds a long-tail test set whose targets are nothing like
    # the organizer's, and misjudges any ranking signal correlated with popularity.
    banded: dict[int, list[dict]] = defaultdict(list)
    for product in candidates:
        banded[_popularity_bucket(int(product.get("rating_number") or 0))].append(product)
    for members in banded.values():
        rng.shuffle(members)

    chosen: list[dict] = []
    references = list(reference_counts)
    rng.shuffle(references)
    populated = sorted(banded)
    for review_count in references:
        if len(chosen) >= sample_count:
            break
        wanted = _popularity_bucket(review_count)
        for band in sorted(populated, key=lambda value: (abs(value - wanted), value)):
            if banded[band]:
                chosen.append(banded[band].pop())
                break
    if len(chosen) < sample_count:
        raise ValueError(f"popularity matching produced only {len(chosen)} targets")
    return chosen


def _conflicting_constraint(
    target: dict, category_products: list[dict], rng: random.Random
) -> str:
    target_text = _normalize(json.dumps(target, ensure_ascii=False))
    alternatives = list(category_products)
    rng.shuffle(alternatives)
    for product in alternatives[:100]:
        if product["parent_asin"] == target["parent_asin"]:
            continue
        card = intent_card(product)
        for value in [*card.get("soft_preferences", []), *card.get("hard_constraints", [])]:
            if _normalize(str(value)) not in target_text:
                return str(value)
    return "a different style"


def _initial_message(scenario: str, category: str, card: dict, old_value: str) -> tuple[str, set[str]]:
    if scenario == "buying":
        value = str(card["hard_constraints"][0])
        return (
            f"Please help me find some {category}. It must have {paraphrase_constraint(value)}.",
            {value},
        )
    if scenario == "intent_override":
        return f"I'm shopping for {category}. {old_value}.", {old_value}
    return f"Could you show me some {category}? I'm open to ideas.", set()


def _customer_reply(
    scenario: str,
    ask_attribute: object,
    constraints: list[str],
    disclosed: set[str],
    boundary_used: bool,
) -> tuple[str, bool]:
    attribute = ask_attribute if isinstance(ask_attribute, str) else None
    if scenario == "boundary" and not boundary_used and attribute:
        return f"I have no preference about {attribute}; use your judgment.", True
    if not attribute:
        return "Those are not right yet. Ask me one focused question.", boundary_used
    matches = [
        value
        for value in constraints
        if value not in disclosed
        and (attribute == "other" or classify_constraint(value) == attribute)
    ][:2]
    if not matches:
        return f"I have no additional preference about {attribute}.", boundary_used
    disclosed.update(matches)
    rendered = "; ".join(paraphrase_constraint(value) for value in matches)
    return f"For {attribute}, I care about: {rendered}.", boundary_used


def run_shadow_evaluation(
    agent: Agent,
    products: dict[str, dict],
    public_samples: list[dict],
    sample_count: int,
    seed: int,
) -> dict:
    excluded_ids = {
        str(sample["ground_truth"]["parent_asin"])
        for sample in public_samples
        if sample.get("ground_truth")
    }
    reference_counts = [
        int(products[str(sample["ground_truth"]["parent_asin"])].get("rating_number") or 0)
        for sample in public_samples
        if sample.get("ground_truth")
        and str(sample["ground_truth"]["parent_asin"]) in products
    ]
    targets = select_targets(products, excluded_ids, sample_count, seed, reference_counts)
    scenarios = scenario_sequence(sample_count, seed)
    catalog_ids = set(products)
    by_category: dict[str, list[dict]] = defaultdict(list)
    for product in products.values():
        by_category[coarse_category([str(v) for v in product.get("categories") or []])].append(product)

    sessions: list[dict] = []
    rng = random.Random(seed)
    for index, (target, scenario) in enumerate(zip(targets, scenarios, strict=True)):
        target_id = str(target["parent_asin"])
        category = coarse_category([str(value) for value in target.get("categories") or []])
        card = intent_card(target)
        constraints = [
            *[str(value) for value in card.get("hard_constraints", [])],
            *[str(value) for value in card.get("soft_preferences", [])],
        ]
        old_value = _conflicting_constraint(target, by_category[category], rng)
        message, disclosed = _initial_message(scenario, category, card, old_value)
        session_id = f"shadow-{seed}-{index}"
        agent.reset(session_id, {"preference_tags": [], "summary": ""})
        boundary_used = False
        first_hit_turn: int | None = None
        best_rank: int | None = None

        for turn in range(1, MAX_TURNS + 1):
            response = agent.respond(session_id, message, turn, TOP_K)
            recommendations = normalize_recommendations(
                response.get("recommendations"), catalog_ids
            )
            if target_id in recommendations and not (
                scenario == "intent_override" and turn < 3
            ):
                rank = recommendations.index(target_id) + 1
                first_hit_turn = turn
                best_rank = rank
                break
            if scenario == "intent_override" and turn == 2:
                replacement = str(card["hard_constraints"][0])
                disclosed.add(replacement)
                message = (
                    "Scratch that earlier requirement; I no longer want it. "
                    f"Instead I need: {paraphrase_constraint(replacement)}."
                )
                continue
            message, boundary_used = _customer_reply(
                scenario,
                response.get("ask_attribute"),
                constraints,
                disclosed,
                boundary_used,
            )

        reciprocal_rank = 1.0 / best_rank if best_rank else 0.0
        sessions.append(
            {
                "scenario_type": scenario,
                "hit": first_hit_turn is not None,
                "first_hit_turn": first_hit_turn,
                "reciprocal_rank": reciprocal_rank,
            }
        )

    def summarize(items: list[dict]) -> dict:
        hit_rate = sum(int(item["hit"]) for item in items) / len(items)
        mrr = statistics.fmean(item["reciprocal_rank"] for item in items)
        mttc = statistics.fmean(
            item["first_hit_turn"] if item["first_hit_turn"] is not None else MAX_TURNS + 1
            for item in items
        )
        return {
            "sample_count": len(items),
            "hit_rate_at_10": round(hit_rate, 6),
            "mrr": round(mrr, 6),
            "mttc": round(mttc, 6),
        }

    aggregate = summarize(sessions)
    efficiency = max(0.0, min(1.0, (11.0 - aggregate["mttc"]) / 10.0))
    result = {
        "benchmark": "catalog-disjoint-paraphrase-v1",
        "seed": seed,
        **aggregate,
        "efficiency": round(efficiency, 6),
        "technical_score": round(
            0.5 * aggregate["hit_rate_at_10"] + 0.3 * aggregate["mrr"] + 0.2 * efficiency,
            6,
        ),
        "scenario_metrics": {
            scenario: summarize([item for item in sessions if item["scenario_type"] == scenario])
            for scenario in ("buying", "browsing", "intent_override", "boundary")
        },
        "disclosures": {
            "public_target_overlap": 0,
            "contains_target_ids": False,
            "constraint_source": "target catalog metadata with deterministic surface paraphrases",
            "target_sampling": "popularity-matched to the public set by review count",
            "limitations": "Synthetic customer policy; not an estimate of organizer private-set performance.",
        },
    }
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the catalog-disjoint paraphrase benchmark.")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--public-set", default="data/public_set.jsonl")
    parser.add_argument("--sample-count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    products = {
        str(product["parent_asin"]): product for product in load_jsonl(args.catalog)
    }
    result = run_shadow_evaluation(
        Agent(args.catalog),
        products,
        load_jsonl(args.public_set),
        args.sample_count,
        args.seed,
    )
    rendered = json.dumps(result, indent=2)
    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)


if __name__ == "__main__":
    main()
