"""Fit a supervised within-tier reranker on the train split.

Collects, for every turn of every train session, the products in the top
coverage tier with features [match_tier, relevance, quality] and a binary label
(is this the target). Fits a pure-Python logistic regression and prints the
frozen weights + feature standardization stats for baking into the agent.

The agent itself is never modified by this script; it only reads the diagnostic
state (`last_ranked`, `last_coverage`, `last_relevance`) that ``respond`` leaves
behind.

Usage:
  python -X utf8 -m scripts.fit_reranker --dataset data/splits/train.jsonl
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import uuid

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


def collect_rows(agent, samples, catalog_ids, categories, products):
    rows: list[dict] = []
    for sample in samples:
        session_id = f"fit_{uuid.uuid4().hex}"
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
        for turn in range(1, MAX_TURNS + 1):
            try:
                response = agent.respond(session_id, user_message, turn, TOP_K)
            except Exception:
                response = {"message": "", "ask_attribute": None, "recommendations": []}
            state = agent._sessions[session_id]
            ranked = state.last_ranked
            coverage = state.last_coverage
            relevance = state.last_relevance
            if ranked:
                top_tier = coverage[ranked[0]][:2]
                for parent_asin in ranked:
                    if coverage[parent_asin][:2] != top_tier:
                        break
                    _hard, _soft, match_tier = coverage[parent_asin]
                    rows.append(
                        {
                            "match_tier": match_tier,
                            "relevance": relevance.get(parent_asin, 0.0),
                            "quality": agent._quality.get(parent_asin, 0.0),
                            "label": 1.0 if parent_asin == target else 0.0,
                        }
                    )
            normalized = normalize_recommendations(
                response.get("recommendations"), catalog_ids
            )
            if override_applied and target in normalized:
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
    return rows


def sigmoid(z: float) -> float:
    z = max(-30.0, min(30.0, z))
    return 1.0 / (1.0 + math.exp(-z))


def fit_logistic(rows: list[dict], epochs: int = 60, lr: float = 0.3):
    names = ("match_tier", "relevance", "quality")
    means = [statistics.mean(row[name] for row in rows) for name in names]
    stds = [statistics.stdev(row[name] for row in rows) or 1.0 for name in names]
    scaled = [
        [(row[name] - mean) / std for name, mean, std in zip(names, means, stds)]
        for row in rows
    ]
    labels = [row["label"] for row in rows]

    weights = [0.0, 0.0, 0.0, 0.0]  # intercept, match_tier, relevance, quality
    for _ in range(epochs):
        grads = [0.0, 0.0, 0.0, 0.0]
        for features, label in zip(scaled, labels):
            z = weights[0] + sum(w * f for w, f in zip(weights[1:], features))
            error = sigmoid(z) - label
            grads[0] += error
            for index in range(3):
                grads[index + 1] += error * features[index]
        for index in range(4):
            weights[index] -= lr * grads[index] / max(1, len(rows))

    positives = sum(labels)
    print(f"training rows: {len(rows)}  positives: {positives:.0f} "
          f"({100.0 * positives / max(1, len(rows)):.2f}%)")
    print("feature means:", {name: round(mean, 6) for name, mean in zip(names, means)})
    print("feature stds:", {name: round(std, 6) for name, std in zip(names, stds)})
    print("weights (intercept, match_tier, relevance, quality):")
    print([round(w, 6) for w in weights])
    return weights, means, stds


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--dataset", default="data/splits/train.jsonl")
    parser.add_argument("--output", default=None)
    args = parser.parse_args()

    samples = load_jsonl(args.dataset)
    catalog_ids, categories, products = catalog_index(args.catalog)
    agent = Agent(args.catalog)
    rows = collect_rows(agent, samples, catalog_ids, categories, products)
    weights, means, stds = fit_logistic(rows)

    if args.output:
        payload = {
            "weights": weights,
            "means": means,
            "stds": stds,
            "feature_names": ["match_tier", "relevance", "quality"],
        }
        with open(args.output, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)
        print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
