"""Attribution benchmark: score + per-session failure classification.

Runs the unmodified evaluator protocol on held-out targets across orthogonal
perturbation axes and reports, for each mode, the aggregate metrics plus:

* how often the target received zero / partial / full hard coverage;
* a per-session miss classification versus the verbatim run:
  ``parser`` (fewer constraints extracted), ``retrieval`` (target got zero hard
  coverage), ``ordering`` (covered but ranked too low), or ``none``.

Usage:
  python -X utf8 -m scripts.bench --dataset data/unseen/unseen_small.jsonl \
      --modes verbatim,typed,synonym,filler,structure,paraphrase,reworded \
      --output results/007_attribution.json
"""

from __future__ import annotations

import argparse
import json
import statistics
import uuid
from collections import defaultdict
from pathlib import Path

from evaluator.local_evaluator import (
    MAX_TURNS,
    TOP_K,
    catalog_index,
    coarse_category,
    customer_reply,
    initial_message,
    load_jsonl,
    materialize_hidden_fields,
    normalize_recommendations,
)
from starter.agent import Agent

from scripts.paraphrase import perturb_message

MODE_AXES = {
    "verbatim": (),
    "typed": ("typed",),
    "synonym": ("synonym",),
    "filler": ("filler",),
    "structure": ("structure",),
    "paraphrase": ("typed", "synonym", "filler"),
    "reworded": ("typed", "synonym", "filler", "structure"),
}


def metric_summary(sessions: list[dict]) -> dict:
    if not sessions:
        return {"sample_count": 0, "hit_rate_at_10": 0.0, "mrr": 0.0, "mttc": None}
    hit_rate = sum(int(s["hit"]) for s in sessions) / len(sessions)
    mrr = statistics.fmean(s["reciprocal_rank"] for s in sessions)
    mttc = statistics.fmean(
        s["first_hit_turn"] if s["first_hit_turn"] is not None else MAX_TURNS + 1
        for s in sessions
    )
    return {
        "sample_count": len(sessions),
        "hit_rate_at_10": round(hit_rate, 6),
        "mrr": round(mrr, 6),
        "mttc": round(mttc, 6),
    }


def run_mode(agent, samples, catalog_ids, categories, products, transform):
    """Mirror the evaluator loop and capture target coverage + extracted state."""
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
        target_hard = 0
        target_soft = 0
        for turn in range(1, MAX_TURNS + 1):
            message = transform(user_message) if transform else user_message
            try:
                response = agent.respond(session_id, message, turn, TOP_K)
            except Exception:
                response = {"message": "", "ask_attribute": None, "recommendations": []}
            if not isinstance(response, dict) or not isinstance(response.get("message"), str):
                response = {"message": "", "ask_attribute": None, "recommendations": []}
            ranked = normalize_recommendations(response.get("recommendations"), catalog_ids)
            state = agent._sessions[session_id]
            hard, soft, _tier = state.last_coverage.get(target, (0, 0, 0))
            target_hard, target_soft = hard, soft
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

        state = agent._sessions[session_id]
        sessions.append(
            {
                "sample_id": sample["sample_id"],
                "scenario_type": sample["scenario_type"],
                "hit": hit_turn is not None,
                "first_hit_turn": hit_turn,
                "best_rank": best_rank,
                "reciprocal_rank": 0.0 if best_rank is None else 1.0 / best_rank,
                "target_hard": target_hard,
                "target_soft": target_soft,
                "hard_extracted": len(state.hard),
                "soft_extracted": len(state.soft),
            }
        )
    return sessions


def classify(verbatim: list[dict], perturbed: list[dict]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for base, mod in zip(verbatim, perturbed):
        if base["hit"] and mod["hit"]:
            counts["none" if mod["best_rank"] <= base["best_rank"] else "ordering"] += 1
        elif base["hit"] and not mod["hit"]:
            if mod["hard_extracted"] < base["hard_extracted"]:
                counts["parser"] += 1
            elif mod["target_hard"] < base["target_hard"]:
                counts["retrieval"] += 1
            else:
                counts["ordering"] += 1
        else:
            counts["none"] += 1
    return dict(counts)


def coverage_histogram(sessions: list[dict]) -> dict[str, int]:
    histogram = {"zero": 0, "one": 0, "multi": 0}
    for session in sessions:
        if session["target_hard"] == 0:
            histogram["zero"] += 1
        elif session["target_hard"] == 1:
            histogram["one"] += 1
        else:
            histogram["multi"] += 1
    return histogram


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--dataset", default="data/unseen/unseen.jsonl")
    parser.add_argument(
        "--modes",
        default="verbatim,paraphrase,reworded",
        help="Comma-separated subset of: " + ",".join(MODE_AXES),
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--intensity", type=float, default=1.0)
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    samples = load_jsonl(args.dataset)
    if args.limit is not None:
        samples = samples[: max(args.limit, 0)]
    catalog_ids, categories, products = catalog_index(args.catalog)
    agent = Agent(args.catalog)

    modes = [mode.strip() for mode in args.modes.split(",") if mode.strip()]
    unknown = [mode for mode in modes if mode not in MODE_AXES]
    if unknown:
        parser.error("unknown modes: " + ",".join(unknown))

    results: dict[str, dict] = {}
    verbatim_sessions: list[dict] | None = None
    for mode in modes:
        axes = MODE_AXES[mode]
        transform = None
        if axes:
            transform = lambda message, axes=axes: perturb_message(
                message, axes, args.intensity
            )
        sessions = run_mode(agent, samples, catalog_ids, categories, products, transform)
        if mode == "verbatim":
            verbatim_sessions = sessions
        results[mode] = {
            **metric_summary(sessions),
            "coverage": coverage_histogram(sessions),
        }
        if verbatim_sessions is not None and mode != "verbatim":
            results[mode]["miss_classification"] = classify(verbatim_sessions, sessions)

    print("=== attribution benchmark ===")
    for mode, result in results.items():
        print(
            f"{mode:<12} n={result['sample_count']:<4} "
            f"Hit@10={result['hit_rate_at_10']:.3f} "
            f"MRR={result['mrr']:.4f} "
            f"MTTC={result['mttc']:.3f} "
            f"coverage={result['coverage']}"
        )
        if "miss_classification" in result:
            print(f"              miss_class={result['miss_classification']}")

    if args.output:
        Path(args.output).write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        print(f"\nwrote {args.output}")


if __name__ == "__main__":
    main()
