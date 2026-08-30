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

Targets are popularity-matched to the public set by default. Official targets are
real purchase records from the Clothing 5-core split and are heavily skewed toward
popular products: their median review count is 7078 against 12 for the catalog as a
whole, and 30.5% of catalog products have fewer than five reviews against 1.0% of
public targets. Sampling the catalog uniformly therefore builds a long-tail test set
whose targets are nothing like the organizer's, and it systematically misjudges any
ranking signal correlated with popularity. Pass --uniform-targets to reproduce the
original uniform sampling.
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import defaultdict
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


def _popularity_bucket(review_count: int) -> int:
    """Coarse log2 band of a product's review count."""
    return int(math.log2(review_count)) if review_count > 0 else -1


def select_targets(
    products: dict[str, dict],
    excluded_ids: set[str],
    sample_count: int,
    seed: int,
    require_two_constraints: bool,
    reference_counts: list[int] | None = None,
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

    rng = random.Random(seed)
    if not reference_counts:
        rng.shuffle(pool)
        return pool[:sample_count], thin

    # Draw one unseen product per reference target from the same log2 review-count
    # band, falling back to the nearest populated band. This reproduces the official
    # popularity profile instead of the catalog's long tail.
    banded: dict[int, list[str]] = defaultdict(list)
    for parent_asin in pool:
        banded[
            _popularity_bucket(int(products[parent_asin].get("rating_number") or 0))
        ].append(parent_asin)
    for members in banded.values():
        rng.shuffle(members)

    chosen: list[str] = []
    taken: set[str] = set()
    references = list(reference_counts)
    rng.shuffle(references)
    populated = sorted(banded)
    for review_count in references:
        if len(chosen) >= sample_count:
            break
        wanted = _popularity_bucket(review_count)
        for band in sorted(populated, key=lambda value: (abs(value - wanted), value)):
            members = banded[band]
            while members:
                candidate = members.pop()
                if candidate not in taken:
                    taken.add(candidate)
                    chosen.append(candidate)
                    break
            else:
                continue
            break
    if len(chosen) < sample_count:
        raise ValueError(f"popularity matching produced only {len(chosen)} targets")
    return chosen, thin


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
        "--uniform-targets",
        action="store_true",
        help=(
            "Sample targets uniformly from the catalog instead of matching the public "
            "set's review-count profile. Reproduces the original, long-tail-biased pool."
        ),
    )
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

    reference_counts = None
    if not args.uniform_targets:
        reference_counts = [
            int(products[str(sample["ground_truth"]["parent_asin"])].get("rating_number") or 0)
            for sample in public_samples
            if sample.get("ground_truth")
            and str(sample["ground_truth"]["parent_asin"]) in products
        ]
    targets, thin = select_targets(
        products,
        excluded,
        args.sample_count,
        args.seed,
        args.require_two_constraints,
        reference_counts,
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
        "target_sampling": "uniform" if args.uniform_targets else "popularity-matched",
        "median_target_review_count": (
            sorted(int(products[t].get("rating_number") or 0) for t in targets)[len(targets) // 2]
        ),
    }
    report["disclosures"] = {
        "limitations": (
            "Assumes the organizer's private harness uses the shipped dialogue policy. "
            "Targets are popularity-matched to the public set by review count unless "
            "--uniform-targets is passed; uniform sampling draws a long tail unlike the "
            "real purchase records the organizer uses. Neutral user profiles are substituted."
        )
    }
    text = json.dumps(report, indent=2)
    print(text)
    if args.output:
        args.output.write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
