"""Official dialogue policy, catalog-disjoint targets: the private-set proxy.

`scripts.shadow_evaluator` changes two things at once relative to the official
evaluator — it targets unseen products *and* rewrites the customer's wording — so
its score cannot attribute the drop to either cause.

This benchmark changes exactly one: the target product. Every message, marker,
and constraint string is produced by the unmodified official simulator in
`evaluator/local_evaluator.py`. It therefore estimates the organizer's private
set under the assumption that the private harness uses the shipped dialogue
policy. Read the two benchmarks together:

* this script  -> unseen products, official wording   (private set as specified)
* shadow_evaluator -> unseen products, rewritten wording (private set if the
  organizer's phrasing differs from the shipped simulator)

The gap between them is the agent's exposure to phrasing it was not tuned on.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from evaluator.local_evaluator import catalog_index, evaluate, intent_card, load_jsonl
from starter.agent import Agent


SCENARIO_BLOCK = (
    *("buying",) * 8,
    *("browsing",) * 8,
    *("intent_override",) * 3,
    "boundary",
)


def scenario_sequence(sample_count: int, seed: int) -> list[str]:
    scenarios = [SCENARIO_BLOCK[index % len(SCENARIO_BLOCK)] for index in range(sample_count)]
    random.Random(seed ^ 0x5EED).shuffle(scenarios)
    return scenarios


def select_targets(
    products: dict[str, dict],
    excluded_ids: set[str],
    sample_count: int,
    seed: int,
    require_two_constraints: bool,
) -> tuple[list[str], int]:
    pool: list[str] = []
    thin = 0
    for parent_asin, product in products.items():
        if parent_asin in excluded_ids or not product.get("categories"):
            continue
        if len(intent_card(product).get("hard_constraints", [])) < 2:
            thin += 1
            if require_two_constraints:
                continue
        pool.append(parent_asin)
    if len(pool) < sample_count:
        raise ValueError(f"requested {sample_count} targets but only {len(pool)} qualify")
    random.Random(seed).shuffle(pool)
    return pool[:sample_count], thin


def build_samples(targets: list[str], scenarios: list[str]) -> list[dict]:
    # The organizer's profiles are not reconstructable for unseen products, so a
    # neutral profile is used. The agent consults the profile only as a low-weight
    # recall route, never as constraint evidence.
    return [
        {
            "sample_id": f"unseen_{index:04d}",
            "scenario_type": scenario,
            "category_bucket": "clothing",
            "difficulty_bucket": "unknown",
            "user_profile": {"preference_tags": [], "summary": "", "average_prior_rating": 4.0},
            "ground_truth": {"parent_asin": parent_asin},
        }
        for index, (parent_asin, scenario) in enumerate(zip(targets, scenarios, strict=True))
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description="Unseen-target official-policy benchmark")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--public-set", default="data/public_set.jsonl")
    parser.add_argument("--sample-count", type=int, default=200)
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument(
        "--require-two-constraints",
        action="store_true",
        help="Skip catalog products whose intent card yields fewer than two hard constraints.",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    catalog_ids, categories, products = catalog_index(args.catalog)
    public_samples = load_jsonl(args.public_set)
    excluded = {
        str(sample["ground_truth"]["parent_asin"])
        for sample in public_samples
        if sample.get("ground_truth")
    }

    targets, thin = select_targets(
        products, excluded, args.sample_count, args.seed, args.require_two_constraints
    )
    samples = build_samples(targets, scenario_sequence(args.sample_count, args.seed))

    agent = Agent(catalog_path=args.catalog)
    report = evaluate(agent, samples, catalog_ids, categories, products)
    report.pop("sessions", None)
    report["config"] = {
        "benchmark": "official-policy-unseen-targets-v1",
        "seed": args.seed,
        "sample_count": args.sample_count,
        "require_two_constraints": args.require_two_constraints,
        "eligible_pool": len(products) - len(excluded),
        "catalog_products_with_thin_constraints": thin,
        "public_target_overlap": 0,
        "dialogue_policy": "unmodified evaluator.local_evaluator",
    }
    report["disclosures"] = {
        "limitations": (
            "Assumes the organizer's private harness uses the shipped dialogue policy. "
            "Targets are sampled uniformly from the catalog, whereas official sessions "
            "derive from the Clothing 5-core review split and may favour products with "
            "richer metadata. Neutral user profiles are substituted."
        )
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
