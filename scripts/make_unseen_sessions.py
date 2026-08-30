"""Generate protocol-compatible sessions for catalog products never used for tuning.

The 200 public sessions were inspected during development, so they are no longer
an unbiased holdout. This script samples fresh target products from
``data/catalog.jsonl`` whose ``parent_asin`` is absent from the public set,
assigns the official scenario mix, reuses the public aggregate profiles
(profiles are not target-specific), and writes evaluator-compatible JSONL.

The public evaluator derives the intent card from the target product metadata
at run time (``materialize_hidden_fields``), so the generated rows need only the
same shape as ``data/public_set.jsonl``: ``sample_id``, ``scenario_type``,
``ground_truth.parent_asin``, and ``user_profile``.

Usage:
  python -m scripts.make_unseen_sessions --n 400 --seed 7
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from evaluator.local_evaluator import catalog_index, load_jsonl


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--public", default="data/public_set.jsonl")
    parser.add_argument("--output", default="data/unseen/unseen.jsonl")
    parser.add_argument("--n", type=int, default=400)
    parser.add_argument("--seed", type=int, default=7)
    args = parser.parse_args()

    catalog_ids, _categories, products = catalog_index(args.catalog)
    public_samples = load_jsonl(args.public)
    public_targets = {
        str(sample["ground_truth"]["parent_asin"]) for sample in public_samples
    }

    candidate_ids = sorted(
        parent_asin for parent_asin in catalog_ids if parent_asin not in public_targets
    )
    if len(candidate_ids) < args.n:
        raise SystemExit(
            f"not enough unseen products: need {args.n}, have {len(candidate_ids)}"
        )

    # Canonical profiles in stable first-seen order, cycled across sessions.
    profiles: list[dict] = []
    seen_profiles: set[str] = set()
    for sample in public_samples:
        key = json.dumps(sample.get("user_profile") or {}, sort_keys=True)
        if key not in seen_profiles:
            seen_profiles.add(key)
            profiles.append(sample["user_profile"])

    rng = random.Random(args.seed)
    rng.shuffle(candidate_ids)

    buying = round(args.n * 0.40)
    browsing = round(args.n * 0.40)
    intent_override = round(args.n * 0.15)
    boundary = args.n - buying - browsing - intent_override

    scenario_blocks = (
        ("buying", buying),
        ("browsing", browsing),
        ("intent_override", intent_override),
        ("boundary", boundary),
    )

    rows: list[dict] = []
    cursor = 0
    index = 0
    for scenario, count in scenario_blocks:
        for _ in range(count):
            parent_asin = candidate_ids[cursor]
            cursor += 1
            rows.append(
                {
                    "sample_id": f"unseen_{index:04d}",
                    "scenario_type": scenario,
                    "ground_truth": {"parent_asin": parent_asin},
                    "user_profile": profiles[index % len(profiles)],
                }
            )
            index += 1

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")

    print(f"wrote {output} ({len(rows)} sessions)")
    print(f"  buying={buying} browsing={browsing} "
          f"intent_override={intent_override} boundary={boundary}")
    print(f"  public targets excluded: {len(public_targets)}")


if __name__ == "__main__":
    main()
