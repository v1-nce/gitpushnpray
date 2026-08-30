"""Deterministic, scenario-stratified train/validation/test split.

The 200 labeled public sessions are the only development data. Reporting the
metric on the same population the agent was tuned on is "training on the test
set": a good score there proves nothing about the 800 private sessions.

This script carves the public set into train / validation / test so that
architecture work happens on train, model selection happens on validation, and
the test split is benchmarked exactly once at the end. The split is reproducible
from ``data/public_set.jsonl`` plus the fixed seed.

Strategy (default):
  * sort samples by ``sample_id`` for a stable input order;
  * stratify by ``scenario_type`` so every split keeps the 40/40/15/5 mix;
  * allocate counts per scenario with largest-remainder rounding;
  * shuffle within each scenario with a seeded RNG.

``--group-by-profile`` additionally treats every sample that shares an identical
``user_profile`` as one atomic group so no profile leaks across splits, at the
cost of less exact scenario proportions.

Usage:
  python -m scripts.make_splits --report
  python -m scripts.make_splits --group-by-profile
"""

from __future__ import annotations

import argparse
import json
import math
import random
from collections import Counter, defaultdict
from pathlib import Path

SCENARIOS = ("buying", "browsing", "intent_override", "boundary")
SPLIT_NAMES = ("train", "val", "test")


def load_samples(path: str | Path) -> list[dict]:
    samples: list[dict] = []
    with Path(path).open(encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                samples.append(json.loads(line))
    samples.sort(key=lambda sample: str(sample["sample_id"]))
    return samples


def profile_key(sample: dict) -> str:
    return json.dumps(sample.get("user_profile") or {}, sort_keys=True)


def allocate(n: int, ratios: tuple[float, ...]) -> list[int]:
    """Largest-remainder allocation of ``n`` items into len(ratios) buckets."""
    total = sum(ratios)
    raw = [n * ratio / total for ratio in ratios]
    base = [math.floor(value) for value in raw]
    remainder = n - sum(base)
    order = sorted(range(len(ratios)), key=lambda index: -(raw[index] - base[index]))
    for index in order[:remainder]:
        base[index] += 1
    return base


def scenario_counts(samples: list[dict]) -> Counter[str]:
    return Counter(str(sample["scenario_type"]) for sample in samples)


def profile_groups(samples: list[dict]) -> list[list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for sample in samples:
        grouped[profile_key(sample)].append(sample)
    return sorted(grouped.values(), key=lambda group: group[0]["sample_id"])


def stratified_split(
    samples: list[dict], ratios: tuple[float, ...], seed: int
) -> list[list[dict]]:
    by_scenario: dict[str, list[dict]] = defaultdict(list)
    for sample in samples:
        by_scenario[str(sample["scenario_type"])].append(sample)

    buckets: list[list[dict]] = [[] for _ in ratios]
    rng = random.Random(seed)
    for scenario in SCENARIOS:
        group = sorted(by_scenario.get(scenario, []), key=lambda sample: sample["sample_id"])
        rng.shuffle(group)
        counts = allocate(len(group), ratios)
        start = 0
        for index, count in enumerate(counts):
            buckets[index].extend(group[start : start + count])
            start += count
    return buckets


def profile_grouped_split(
    samples: list[dict], ratios: tuple[float, ...], seed: int
) -> list[list[dict]]:
    """Greedy atomic assignment: a whole profile group goes to one split.

    Groups are sorted by size descending, then assigned to the split whose
    current sample count is furthest below its target share. This keeps overall
    size ratios close while guaranteeing a profile never appears in two splits.
    """
    groups = profile_groups(samples)
    groups.sort(key=lambda group: (-len(group), group[0]["sample_id"]))
    total = len(samples)
    target = [total * ratio / sum(ratios) for ratio in ratios]
    buckets: list[list[dict]] = [[] for _ in ratios]
    rng = random.Random(seed)
    for group in groups:
        rng.shuffle(group)
        # Pick the split with the largest remaining deficit, breaking ties
        # with a seeded coin flip so the assignment stays reproducible.
        deficit = [target[index] - len(buckets[index]) for index in range(len(ratios))]
        best = max(range(len(ratios)), key=lambda index: (deficit[index], rng.random()))
        buckets[best].extend(group)
    return buckets


def cross_split_profile_leakage(buckets: list[list[dict]]) -> Counter[str]:
    """Count profiles that appear in more than one split."""
    owner: dict[str, str] = {}
    leakage: Counter[str] = Counter()
    for name, bucket in zip(SPLIT_NAMES, buckets):
        for sample in bucket:
            key = profile_key(sample)
            if key in owner and owner[key] != name:
                leakage[f"{owner[key]}<->{name}"] += 1
            owner[key] = name
    return leakage


def format_counts(buckets: list[list[dict]]) -> str:
    lines: list[str] = []
    for name, bucket in zip(SPLIT_NAMES, buckets):
        counts = scenario_counts(bucket)
        breakdown = " ".join(
            f"{scenario}={counts.get(scenario, 0)}" for scenario in SCENARIOS
        )
        lines.append(f"  {name:>5}: n={len(bucket):>3}  {breakdown}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", default="data/public_set.jsonl")
    parser.add_argument("--output-dir", default="data/splits")
    parser.add_argument("--ratios", nargs=3, type=float, default=(0.6, 0.2, 0.2))
    parser.add_argument("--seed", type=int, default=20260830)
    parser.add_argument("--group-by-profile", action="store_true")
    parser.add_argument(
        "--report",
        action="store_true",
        help="Print split composition and profile leakage without writing files.",
    )
    args = parser.parse_args()

    if any(ratio <= 0 for ratio in args.ratios):
        parser.error("ratios must all be positive")
    ratios = tuple(args.ratios)

    samples = load_samples(args.dataset)
    if not samples:
        parser.error(f"no samples in {args.dataset}")

    canonical_profiles = len({profile_key(sample) for sample in samples})
    print(f"source: {args.dataset}")
    print(f"samples: {len(samples)}  canonical profiles: {canonical_profiles}")

    if args.group_by_profile:
        buckets = profile_grouped_split(samples, ratios, args.seed)
        method = "profile-grouped (no profile crosses splits)"
    else:
        buckets = stratified_split(samples, ratios, args.seed)
        method = "scenario-stratified"
    print(f"method: {method}  ratios: {ratios}  seed: {args.seed}")
    print(format_counts(buckets))

    leakage = cross_split_profile_leakage(buckets)
    print(f"cross-split profile leakage: {dict(leakage) if leakage else 'none'}")

    if args.report:
        return

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, bucket in zip(SPLIT_NAMES, buckets):
        bucket.sort(key=lambda sample: sample["sample_id"])
        path = output_dir / f"{name}.jsonl"
        with path.open("w", encoding="utf-8") as handle:
            for sample in bucket:
                handle.write(json.dumps(sample) + "\n")
        print(f"wrote {path} ({len(bucket)} samples)")


if __name__ == "__main__":
    main()
