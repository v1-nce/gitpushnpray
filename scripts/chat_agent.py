"""Manually role-play a customer looking for a known catalog product."""

from __future__ import annotations

import argparse
import json
import random
import sys
import uuid
from pathlib import Path

from starter.agent import Agent


def load_catalog(
    catalog_path: Path,
    requested_target: str | None,
    seed: int,
) -> tuple[dict[str, str], dict]:
    titles: dict[str, str] = {}
    target_product: dict | None = None
    rng = random.Random(seed)
    seen = 0
    with catalog_path.open(encoding="utf-8") as handle:
        for line in handle:
            product = json.loads(line)
            parent_asin = str(product["parent_asin"])
            titles[parent_asin] = str(product.get("title") or "Untitled product")
            if requested_target is not None:
                if parent_asin == requested_target:
                    target_product = product
            else:
                seen += 1
                if rng.randrange(seen) == 0:
                    target_product = product
    if target_product is None:
        raise ValueError(f"Target ASIN not found: {requested_target}")
    return titles, target_product


def display_target(product: dict) -> None:
    print("\nPRODUCT TO ROLE-PLAY")
    print(f"ASIN: {product['parent_asin']}")
    print(f"Title: {product.get('title')}")
    print(f"Categories: {' > '.join(str(value) for value in product.get('categories') or [])}")
    print(f"Price: {product.get('price')}")
    features = [str(value) for value in product.get("features") or []]
    if features:
        print("Product evidence:")
        for feature in features[:6]:
            print(f"  - {feature}")
    print(
        "\nDescribe the product naturally. For a stronger stress test, avoid copying the "
        "title or feature sentences word-for-word. Type /quit to stop."
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Chat with the shopping agent while role-playing a known target product."
    )
    target_group = parser.add_mutually_exclusive_group(required=True)
    target_group.add_argument("--target", help="Catalog parent_asin to use as the hidden target.")
    target_group.add_argument(
        "--random",
        action="store_true",
        help="Choose a deterministic random catalog product.",
    )
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--top-n", type=int, default=10)
    args = parser.parse_args()

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    catalog_path = Path(args.catalog)
    titles, target_product = load_catalog(
        catalog_path,
        None if args.random else args.target,
        args.seed,
    )
    display_target(target_product)
    print("\nBuilding the in-memory search indexes...")
    agent = Agent(catalog_path)
    session_id = f"manual_{uuid.uuid4().hex}"
    agent.reset(
        session_id,
        {
            "purchase_frequency": "unknown",
            "average_prior_rating": None,
            "rating_style": "unknown",
            "preference_tags": [],
            "summary": "",
        },
    )
    target = str(target_product["parent_asin"])
    top_n = min(max(args.top_n, 0), 10)

    for turn in range(1, 11):
        try:
            user_message = input(f"\nYOU — turn {turn}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nStopped.")
            return
        if user_message.lower() == "/quit":
            print("Stopped.")
            return
        if not user_message:
            print("Please enter a message or /quit.")
            continue

        response = agent.respond(session_id, user_message, turn, 10)
        print(f"AGENT: {response['message']}")
        print(f"ASK ATTRIBUTE: {response['ask_attribute']!r}")
        ranked = [str(item["parent_asin"]) for item in response["recommendations"]]
        for rank, parent_asin in enumerate(ranked[:top_n], start=1):
            marker = "  <-- YOUR TARGET" if parent_asin == target else ""
            print(f"  {rank:>2}. {parent_asin} | {titles.get(parent_asin, '')}{marker}")
        if target in ranked:
            rank = ranked.index(target) + 1
            print(f"\nHIT: the target appeared at rank {rank} on turn {turn}.")
            return
        print("TARGET: not in this turn's Top 10.")

    print("\nMISS: the target never appeared in the Top 10 within 10 turns.")


if __name__ == "__main__":
    main()
