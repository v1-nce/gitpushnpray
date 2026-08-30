"""Reproducible end-to-end demo transcript for the shopping copilot.

Runs one labeled session through the agent and prints a clean, human-readable
transcript suitable for the demo video and README. Optionally writes Markdown.

Usage:
  python -X utf8 -m scripts.demo --sample public_0001
  python -X utf8 -m scripts.demo --sample unseen_0001 --dataset data/unseen/unseen.jsonl
"""

from __future__ import annotations

import argparse
import json
import uuid
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


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sample", default="public_0001")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--dataset", default="data/public_set.jsonl")
    parser.add_argument("--output", default=None, help="Write Markdown to this path.")
    args = parser.parse_args()

    samples = load_jsonl(args.dataset)
    by_id = {sample["sample_id"]: sample for sample in samples}
    sample = by_id.get(args.sample)
    if sample is None:
        raise SystemExit(f"sample {args.sample} not found in {args.dataset}")

    catalog_ids, categories, products = catalog_index(args.catalog)
    target = str(sample["ground_truth"]["parent_asin"])
    card, behavior = materialize_hidden_fields(sample, products)
    effective = {**sample, "intent_card": card, "behavior": behavior}

    agent = Agent(args.catalog)
    session_id = f"demo_{uuid.uuid4().hex}"
    agent.reset(session_id, sample["user_profile"])

    disclosed: set[str] = set()
    boundary_used = False
    override_applied = sample["scenario_type"] != "intent_override"
    user_message = initial_message(
        effective, coarse_category(categories.get(target, [])), disclosed
    )

    lines: list[str] = []
    lines.append("# Shopping Copilot — End-to-End Demo")
    lines.append("")
    lines.append(f"**Scenario:** {sample['scenario_type']} · "
                 f"**Sample:** {sample['sample_id']}")
    lines.append("")
    lines.append(f"**Hidden target:** `{target}` · {products[target].get('title')}")
    lines.append("")

    for turn in range(1, MAX_TURNS + 1):
        response = agent.respond(session_id, user_message, turn, TOP_K)
        ranked = normalize_recommendations(response.get("recommendations"), catalog_ids)
        rank = ranked.index(target) + 1 if target in ranked else None

        lines.append(f"## Turn {turn}")
        lines.append("")
        lines.append(f"**Customer:** {user_message}")
        lines.append("")
        lines.append(f"**Agent:** {response.get('message')} "
                     f"`ask_attribute={response.get('ask_attribute')!r}`")
        lines.append("")
        lines.append("**Recommendations:**")
        for position, parent_asin in enumerate(ranked, start=1):
            marker = "  ← target" if parent_asin == target else ""
            lines.append(f"{position}. `{parent_asin}` — "
                         f"{products.get(parent_asin, {}).get('title', '')}{marker}")
        lines.append("")

        if override_applied and rank is not None:
            lines.append(f"**HIT** — target found at rank {rank} on turn {turn}.")
            lines.append("")
            break
        if turn == MAX_TURNS:
            lines.append("**MISS** — target not found within 10 turns.")
            lines.append("")
            break

        override = effective.get("behavior", {}).get("override") or {}
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
                effective, response.get("ask_attribute"), disclosed, boundary_used
            )

    text = "\n".join(lines)
    print(text)
    if args.output:
        Path(args.output).write_text(text, encoding="utf-8")
        print(f"\nwrote {args.output}")


if __name__ == "__main__":
    main()
