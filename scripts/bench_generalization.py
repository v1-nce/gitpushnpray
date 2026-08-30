"""Benchmark the agent on unseen-catalog sessions, verbatim and paraphrased.

The official evaluator is reused unchanged for scoring; this script only adds a
conversation loop that can transform each customer message before it reaches
the agent. That loop is validated against the official ``evaluate()`` on the
verbatim pass so a divergence is caught immediately.

Modes:
  verbatim    official messages (baseline)
  paraphrase  constraint payloads reworded, markers kept (tests retrieval)
  reworded    structure and payload reworded (tests parser + retrieval)

Usage:
  python -m scripts.make_unseen_sessions --n 400
  python -X utf8 -m scripts.bench_generalization --dataset data/unseen/unseen.jsonl --mode all
"""

from __future__ import annotations

import argparse
import json
import uuid
from collections import defaultdict
from pathlib import Path

from evaluator.local_evaluator import (
    MAX_TURNS,
    TOP_K,
    catalog_index,
    coarse_category,
    customer_reply,
    evaluate,
    initial_message,
    load_jsonl,
    materialize_hidden_fields,
    metric_summary,
    normalize_recommendations,
)
from starter.agent import Agent

from scripts.paraphrase import paraphrase_message, reword_message


def run_sessions(agent, samples, catalog_ids, categories, products, transform=None):
    """Mirror ``evaluate()`` but optionally transform each customer message."""
    sessions: list[dict] = []
    for sample in samples:
        session_id = f"bench_{uuid.uuid4().hex}"
        agent.reset(session_id, sample["user_profile"])
        target = str(sample["ground_truth"]["parent_asin"])
        card, behavior = materialize_hidden_fields(sample, products)
        effective_sample = {**sample, "intent_card": card, "behavior": behavior}
        disclosed: set[str] = set()
        boundary_used = False
        override_applied = sample["scenario_type"] != "intent_override"
        user_message = initial_message(
            effective_sample, coarse_category(categories.get(target, [])), disclosed
        )
        hit_turn: int | None = None
        best_rank: int | None = None
        for turn in range(1, MAX_TURNS + 1):
            message = transform(user_message) if transform else user_message
            try:
                response = agent.respond(session_id, message, turn, TOP_K)
            except Exception:
                response = {"message": "", "ask_attribute": None, "recommendations": []}
            if not isinstance(response, dict) or not isinstance(response.get("message"), str):
                response = {"message": "", "ask_attribute": None, "recommendations": []}
            ranked = normalize_recommendations(response.get("recommendations"), catalog_ids)
            if override_applied and target in ranked:
                best_rank = ranked.index(target) + 1
                hit_turn = turn
                break
            if turn == MAX_TURNS:
                break
            override = effective_sample.get("behavior", {}).get("override") or {}
            if not override_applied and turn + 1 == int(override.get("turn", 3)):
                override_applied = True
                new_value = str(override.get("new_value", ""))
                if new_value:
                    disclosed.add(new_value)
                user_message = str(
                    override.get("message", "Actually, please ignore my earlier preference.")
                )
            else:
                user_message, boundary_used = customer_reply(
                    effective_sample, response.get("ask_attribute"), disclosed, boundary_used
                )
        sessions.append(
            {
                "sample_id": sample["sample_id"],
                "scenario_type": sample["scenario_type"],
                "hit": hit_turn is not None,
                "first_hit_turn": hit_turn,
                "best_rank": best_rank,
                "reciprocal_rank": 0.0 if best_rank is None else 1.0 / best_rank,
            }
        )

    overall = metric_summary(sessions)
    efficiency = max(0.0, min(1.0, (11.0 - float(overall["mttc"])) / 10.0))
    technical_score = 0.50 * overall["hit_rate_at_10"] + 0.30 * overall["mrr"] + 0.20 * efficiency
    grouped: dict[str, list[dict]] = defaultdict(list)
    for session in sessions:
        grouped[session["scenario_type"]].append(session)
    return {
        **overall,
        "efficiency": round(efficiency, 6),
        "recommended_technical_score": round(technical_score, 6),
        "scenario_metrics": {name: metric_summary(grouped[name]) for name in sorted(grouped)},
        "sessions": sessions,
    }


def print_metrics(label: str, result: dict) -> None:
    print(
        f"{label:<12} n={result['sample_count']:<4} "
        f"Hit@10={result['hit_rate_at_10']:.3f} "
        f"MRR={result['mrr']:.4f} "
        f"MTTC={result['mttc']:.3f} "
        f"score={result['recommended_technical_score']:.4f}"
    )
    for scenario, metrics in result["scenario_metrics"].items():
        print(
            f"  {scenario:<15} n={metrics['sample_count']:<3} "
            f"Hit@10={metrics['hit_rate_at_10']:.3f} "
            f"MRR={metrics['mrr']:.4f} "
            f"MTTC={metrics['mttc']:.3f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--dataset", default="data/unseen/unseen.jsonl")
    parser.add_argument(
        "--mode",
        choices=("verbatim", "paraphrase", "reworded", "all"),
        default="all",
    )
    parser.add_argument("--limit", type=int, default=None, help="Run on the first N samples only.")
    parser.add_argument("--output", default=None, help="Optional JSON output path.")
    args = parser.parse_args()

    samples = load_jsonl(args.dataset)
    if args.limit is not None:
        samples = samples[: max(args.limit, 0)]
    catalog_ids, categories, products = catalog_index(args.catalog)
    agent = Agent(args.catalog)

    results: dict[str, dict] = {}

    if args.mode in ("verbatim", "all"):
        # Official evaluator for the verbatim baseline.
        official = evaluate(agent, samples, catalog_ids, categories, products)
        # Independent loop (identity transform) as a self-check.
        loop = run_sessions(agent, samples, catalog_ids, categories, products, transform=None)
        per_session_matches = all(
            a["hit"] == b["hit"] and a["first_hit_turn"] == b["first_hit_turn"]
            and a["best_rank"] == b["best_rank"]
            for a, b in zip(official["sessions"], loop["sessions"])
        )
        print(f"verbatim self-check: official==loop -> {per_session_matches}")
        results["verbatim"] = {key: value for key, value in official.items() if key != "sessions"}

    if args.mode in ("paraphrase", "all"):
        results["paraphrase"] = {
            key: value
            for key, value in run_sessions(
                agent, samples, catalog_ids, categories, products, transform=paraphrase_message
            ).items()
            if key != "sessions"
        }

    if args.mode in ("reworded", "all"):
        results["reworded"] = {
            key: value
            for key, value in run_sessions(
                agent, samples, catalog_ids, categories, products, transform=reword_message
            ).items()
            if key != "sessions"
        }

    print("\n=== generalization benchmark ===")
    for label, result in results.items():
        print_metrics(label, result)

    if args.output:
        Path(args.output).write_text(
            json.dumps(results, indent=2) + "\n", encoding="utf-8"
        )
        print(f"\nwrote {args.output}")


if __name__ == "__main__":
    main()
