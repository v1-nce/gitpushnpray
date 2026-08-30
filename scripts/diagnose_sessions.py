"""Trace public evaluator conversations without changing runtime agent features."""

from __future__ import annotations

import argparse

from evaluator.local_evaluator import (
    TOP_K,
    catalog_index,
    coarse_category,
    customer_reply,
    initial_message,
    load_jsonl,
    materialize_hidden_fields,
    normalize_recommendations,
)
from starter.agent import Agent, _normalize_evidence


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Replay public evaluator sessions and display the agent's ranked products."
    )
    parser.add_argument("sample_ids", nargs="*", help="For example: public_0001 public_0002")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--dataset", default="data/public_set.jsonl")
    parser.add_argument(
        "--scenario",
        choices=("buying", "browsing", "intent_override", "boundary"),
        help="Filter sessions when no sample IDs are supplied.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1,
        help="Number of filtered sessions to replay when no sample IDs are supplied.",
    )
    parser.add_argument(
        "--top-n",
        type=int,
        default=5,
        help="Number of ranked recommendation titles to display per turn (0-10).",
    )
    args = parser.parse_args()

    all_samples = load_jsonl(args.dataset)
    if args.sample_ids:
        requested = set(args.sample_ids)
        samples = [sample for sample in all_samples if sample["sample_id"] in requested]
        missing = requested - {sample["sample_id"] for sample in samples}
        if missing:
            parser.error("unknown sample IDs: " + ", ".join(sorted(missing)))
    else:
        samples = [
            sample
            for sample in all_samples
            if args.scenario is None or sample["scenario_type"] == args.scenario
        ][:max(args.limit, 0)]
    top_n = min(max(args.top_n, 0), TOP_K)
    catalog_ids, categories, products = catalog_index(args.catalog)
    agent = Agent(args.catalog)

    for sample in samples:
        target = str(sample["ground_truth"]["parent_asin"])
        card, behavior = materialize_hidden_fields(sample, products)
        effective_sample = {**sample, "intent_card": card, "behavior": behavior}
        disclosed: set[str] = set()
        boundary_used = False
        override_applied = sample["scenario_type"] != "intent_override"
        user_message = initial_message(
            effective_sample,
            coarse_category(categories.get(target, [])),
            disclosed,
        )
        session_id = f"diagnostic_{sample['sample_id']}"
        agent.reset(session_id, sample["user_profile"])

        print(
            f"\n=== {sample['sample_id']} | {sample['scenario_type']} | "
            f"difficulty={sample.get('difficulty_bucket')} ==="
        )
        print(f"HIDDEN TARGET: {target} | {products[target].get('title')}")
        for turn in range(1, 11):
            response = agent.respond(session_id, user_message, turn, TOP_K)
            ranked = normalize_recommendations(response.get("recommendations"), catalog_ids)
            rank = ranked.index(target) + 1 if target in ranked else None
            print(f"\nTURN {turn}")
            print(f"CUSTOMER: {user_message}")
            print(
                f"AGENT: {response.get('message')} "
                f"[ask_attribute={response.get('ask_attribute')!r}]"
            )
            for position, parent_asin in enumerate(ranked[:top_n], start=1):
                marker = "  <-- TARGET" if parent_asin == target else ""
                title = products.get(parent_asin, {}).get("title", "")
                print(f"  {position:>2}. {parent_asin} | {title}{marker}")
            if rank is None:
                print("TARGET STATUS: not in Top 10")
            elif override_applied:
                print(f"TARGET STATUS: HIT at rank {rank}")
            else:
                print(f"TARGET STATUS: rank {rank}, but not scorable until the override")
            if override_applied and rank is not None:
                break
            if turn == 10:
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
                    effective_sample,
                    response.get("ask_attribute"),
                    disclosed,
                    boundary_used,
                )

        state = agent._sessions[session_id]
        print(f"\nRESOLVED CATEGORY: {state.category!r}")
        for constraint in state.constraints:
            normalized = _normalize_evidence(constraint)
            total, target_rows = agent.connection.execute(
                "SELECT COUNT(*), SUM(parent_asin = ?) FROM evidence WHERE normalized = ?",
                (target, normalized),
            ).fetchone()
            print(
                f"EVIDENCE: catalog_matches={total} contains_target={bool(target_rows)} "
                f"value={constraint!r}"
            )


if __name__ == "__main__":
    main()
