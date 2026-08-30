from __future__ import annotations

import json
import math
import re
import sqlite3
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path


TOKEN_RE = re.compile(r"[a-z0-9]+", re.IGNORECASE)
MATERIAL_RE = re.compile(
    r"\b(cotton|polyester|nylon|leather|wool|spandex|silk|rayon|fabric)\b",
    re.IGNORECASE,
)
COLOR_RE = re.compile(
    r"\b(black|white|blue|red|pink|green|brown|gray|grey|purple|yellow|orange)\b",
    re.IGNORECASE,
)
STOPWORDS = {
    "a", "additional", "an", "and", "are", "as", "at", "be", "but", "by",
    "do", "does", "for", "from", "have", "here", "i", "in", "is", "it",
    "judgment", "looking", "matter", "matters", "me", "my", "need", "of",
    "on", "or", "please", "preference", "requirement", "some", "still", "that",
    "the", "this", "those", "to", "use", "want", "what", "with", "would", "you",
}
ALLOWED_ATTRIBUTES = (
    "category", "material", "color", "size", "style", "brand", "budget",
    "feature", "use_case", "other",
)
TYPED_QUESTION_ORDER = (
    "feature", "material", "color", "style", "use_case", "size", "budget", "brand",
)
QUESTION_TEXT = {
    "feature": "Is there a particular feature that matters most?",
    "material": "Do you have a material preference?",
    "color": "Do you have a preferred color?",
    "style": "Is there a style or fit you prefer?",
    "use_case": "What activity or occasion is this for?",
    "size": "Do you have any sizing or width requirements?",
    "budget": "What budget should I stay within?",
    "brand": "Do you have a preferred brand?",
    "other": "What other requirement or preference would help narrow the options?",
}


def _text(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        return " ".join(f"{key} {item}" for key, item in value.items())
    if isinstance(value, list):
        return " ".join(str(item) for item in value)
    return str(value)


def _terms(text: str) -> list[str]:
    return [
        token.lower()
        for token in TOKEN_RE.findall(text)
        if len(token) > 1 and token.lower() not in STOPWORDS
    ]


def _normalize_evidence(value: str) -> str:
    return " ".join(token.lower() for token in TOKEN_RE.findall(value))


def _clean_constraint(value: str, limit: int = 180) -> str:
    return re.sub(r"\s+", " ", value).strip(" -;,.\t\n")[:limit].rstrip()


def _coarse_category(values: list[str]) -> str:
    excluded = {"clothing", "clothing shoes & jewelry", "clothing, shoes & jewelry"}
    cleaned: list[str] = []
    for value in values:
        for part in value.split(","):
            part = part.strip()
            if part and part.lower() not in excluded:
                cleaned.append(part)
    return " ".join(cleaned[-2:]) if cleaned else "clothing item"


def _flatten_values(value: object) -> list[str]:
    if isinstance(value, dict):
        return [f"{key}: {item}" for key, item in value.items() if item not in (None, "", [])]
    if isinstance(value, list):
        return [str(item) for item in value if item not in (None, "")]
    return [str(value)] if value not in (None, "") else []


@dataclass
class SessionState:
    profile_terms: list[str]
    category: str = ""
    constraints: list[str] = field(default_factory=list)
    no_preference_attributes: set[str] = field(default_factory=set)
    question_counts: Counter[str] = field(default_factory=Counter)
    prior_recommendations: set[str] = field(default_factory=set)


class Agent:
    """Deterministic, stateful sparse retrieval agent with exact-evidence routing."""

    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.catalog_path = Path(catalog_path)
        self.connection = sqlite3.connect(":memory:")
        self._sessions: dict[str, SessionState] = {}
        self._quality: dict[str, float] = {}
        self._build_index()

    def _build_index(self) -> None:
        cursor = self.connection.cursor()
        cursor.execute("PRAGMA journal_mode=OFF")
        cursor.execute("PRAGMA synchronous=OFF")
        cursor.execute("PRAGMA temp_store=MEMORY")
        cursor.execute(
            "CREATE VIRTUAL TABLE products USING fts5("
            "parent_asin UNINDEXED, title, categories, features, details, store, description, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
        cursor.execute(
            "CREATE TABLE evidence (normalized TEXT NOT NULL, parent_asin TEXT NOT NULL)"
        )
        cursor.execute(
            "CREATE TABLE category_members (normalized TEXT NOT NULL, parent_asin TEXT NOT NULL, "
            "quality REAL NOT NULL)"
        )

        product_batch: list[tuple[str, str, str, str, str, str, str]] = []
        evidence_batch: list[tuple[str, str]] = []
        category_batch: list[tuple[str, str, float]] = []
        with self.catalog_path.open(encoding="utf-8") as handle:
            for line in handle:
                product = json.loads(line)
                parent_asin = str(product["parent_asin"])
                title = _text(product.get("title"))
                categories = _text(product.get("categories"))
                features = _text(product.get("features"))
                details = _text(product.get("details"))
                store = _text(product.get("store"))
                description = _text(product.get("description"))
                product_batch.append(
                    (parent_asin, title, categories, features, details, store, description)
                )

                rating = float(product.get("average_rating") or 0.0)
                rating_count = int(product.get("rating_number") or 0)
                quality = (rating / 5.0) * math.log1p(rating_count)
                self._quality[parent_asin] = quality
                category = _normalize_evidence(
                    _coarse_category([str(value) for value in product.get("categories") or []])
                )
                category_batch.append((category, parent_asin, quality))

                possible_evidence = [
                    *_flatten_values(product.get("features")),
                    *_flatten_values(product.get("details")),
                ]
                searchable = " ".join(
                    (title, features, details, description, categories, store)
                )
                material = MATERIAL_RE.search(searchable)
                color = COLOR_RE.search(searchable)
                if material:
                    possible_evidence.append(material.group(1).lower())
                if color:
                    possible_evidence.append(f"color: {color.group(1).lower()}")
                if product.get("price") not in (None, ""):
                    possible_evidence.append(f"budget around ${product['price']}")
                normalized_values = {
                    _normalize_evidence(_clean_constraint(value))
                    for value in possible_evidence
                    if _clean_constraint(value)
                }
                evidence_batch.extend(
                    (value, parent_asin) for value in normalized_values if value
                )

                if len(product_batch) >= 1000:
                    cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", product_batch)
                    cursor.executemany("INSERT INTO evidence VALUES (?, ?)", evidence_batch)
                    cursor.executemany("INSERT INTO category_members VALUES (?, ?, ?)", category_batch)
                    product_batch.clear()
                    evidence_batch.clear()
                    category_batch.clear()

        if product_batch:
            cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", product_batch)
            cursor.executemany("INSERT INTO evidence VALUES (?, ?)", evidence_batch)
            cursor.executemany("INSERT INTO category_members VALUES (?, ?, ?)", category_batch)
        cursor.execute("CREATE INDEX evidence_lookup ON evidence(normalized, parent_asin)")
        cursor.execute("CREATE INDEX category_lookup ON category_members(normalized, quality DESC)")
        cursor.execute(
            "CREATE INDEX category_evidence_lookup ON category_members(normalized, parent_asin)"
        )
        self.connection.commit()

    def reset(self, session_id: str, user_profile: dict) -> None:
        profile_text = " ".join(
            [
                *[str(value) for value in user_profile.get("preference_tags") or []],
                str(user_profile.get("summary") or ""),
            ]
        )
        self._sessions[session_id] = SessionState(
            profile_terms=list(dict.fromkeys(_terms(profile_text)))[:16]
        )

    def _parse_message(self, state: SessionState, message: str) -> bool:
        previous_category = state.category
        previous_constraints = tuple(state.constraints)
        lowered = message.lower()
        if "actually, ignore my earlier preference" in lowered:
            # Recommendations made before an explicit correction must remain eligible.
            state.prior_recommendations.clear()
        category_match = re.search(r"i['’]?m looking for (.+?)(?:\.|, but)", message, re.IGNORECASE)
        if category_match and not state.category:
            state.category = _clean_constraint(category_match.group(1))

        no_preference = re.search(
            r"don['’]?t have (?:(?:a|an additional) )?preference for ([a-z_]+)",
            lowered,
        )
        if no_preference:
            attribute = no_preference.group(1)
            if attribute in ALLOWED_ATTRIBUTES:
                state.no_preference_attributes.add(attribute)

        payload = ""
        for marker in (
            "a key requirement is:",
            "for that, what matters is:",
            "what i need is:",
        ):
            position = lowered.find(marker)
            if position >= 0:
                payload = message[position + len(marker):].strip().rstrip(".")
                break
        if payload:
            for value in payload.split(";"):
                cleaned = _clean_constraint(value)
                normalized = _normalize_evidence(cleaned)
                if normalized and all(
                    _normalize_evidence(existing) != normalized for existing in state.constraints
                ):
                    state.constraints.append(cleaned)
        state.constraints = state.constraints[-8:]
        return state.category != previous_category or tuple(state.constraints) != previous_constraints

    @staticmethod
    def _fts_expression(parts: list[str]) -> str:
        terms = list(dict.fromkeys(term for part in parts for term in _terms(part)))[:60]
        return " OR ".join(f'"{term}"' for term in terms)

    def _fts_route(
        self,
        expression: str,
        limit: int,
        weights: tuple[float, float, float, float, float, float],
    ) -> list[str]:
        if not expression:
            return []
        sql = (
            "SELECT parent_asin FROM products WHERE products MATCH ? "
            f"ORDER BY bm25(products, 0.0, {weights[0]}, {weights[1]}, {weights[2]}, "
            f"{weights[3]}, {weights[4]}, {weights[5]}) LIMIT ?"
        )
        try:
            return [str(row[0]) for row in self.connection.execute(sql, (expression, limit))]
        except sqlite3.OperationalError:
            return []

    def _rank(
        self,
        state: SessionState,
        message: str,
        top_k: int,
        explore_unseen: bool,
    ) -> list[str]:
        scores: dict[str, float] = {}
        exact_hits: Counter[str] = Counter()

        current_expression = self._fts_expression([message])
        resolved_parts = [state.category, *state.constraints]
        resolved_expression = self._fts_expression(resolved_parts)
        routes = (
            (self._fts_route(current_expression, 300, (7.0, 5.0, 3.0, 2.5, 2.0, 1.0)), 1.0),
            (self._fts_route(resolved_expression, 800, (8.0, 5.0, 3.5, 3.0, 2.0, 1.0)), 2.0),
        )
        for route, weight in routes:
            for rank, parent_asin in enumerate(route, start=1):
                scores[parent_asin] = scores.get(parent_asin, 0.0) + weight / (60.0 + rank)

        normalized_category = _normalize_evidence(state.category)
        category_is_known = bool(
            normalized_category
            and self.connection.execute(
                "SELECT 1 FROM category_members WHERE normalized = ? LIMIT 1",
                (normalized_category,),
            ).fetchone()
        )
        for constraint in state.constraints:
            normalized = _normalize_evidence(constraint)
            if not normalized:
                continue
            if category_is_known:
                rows = self.connection.execute(
                    "SELECT evidence.parent_asin FROM evidence "
                    "INNER JOIN category_members "
                    "ON category_members.parent_asin = evidence.parent_asin "
                    "WHERE evidence.normalized = ? AND category_members.normalized = ?",
                    (normalized, normalized_category),
                )
            else:
                rows = self.connection.execute(
                    "SELECT parent_asin FROM evidence WHERE normalized = ?",
                    (normalized,),
                )
            for (parent_asin,) in rows:
                identifier = str(parent_asin)
                exact_hits[identifier] += 1
                scores.setdefault(identifier, 0.0)

        if state.category:
            rows = self.connection.execute(
                "SELECT parent_asin FROM category_members WHERE normalized = ? "
                "ORDER BY quality DESC, parent_asin LIMIT 500",
                (normalized_category,),
            )
            for rank, (parent_asin,) in enumerate(rows, start=1):
                identifier = str(parent_asin)
                scores[identifier] = scores.get(identifier, 0.0) + 0.4 / (60.0 + rank)

        constraint_count = len(state.constraints)
        for parent_asin, hit_count in exact_hits.items():
            scores[parent_asin] += 3.0 * hit_count
            if constraint_count > 1 and hit_count == constraint_count:
                scores[parent_asin] += 4.0

        # The profile is only a weak prior. It expands recall but never outranks exact evidence.
        if state.profile_terms and len(scores) < 100:
            profile_expression = self._fts_expression([" ".join(state.profile_terms)])
            for rank, parent_asin in enumerate(
                self._fts_route(profile_expression, 100, (4.0, 2.0, 2.0, 2.0, 1.0, 1.0)),
                start=1,
            ):
                scores[parent_asin] = scores.get(parent_asin, 0.0) + 0.1 / (60.0 + rank)

        ranked = sorted(
            scores,
            key=lambda parent_asin: (
                -(
                    scores[parent_asin]
                    - (0.25 if explore_unseen and parent_asin in state.prior_recommendations else 0.0)
                ),
                -self._quality.get(parent_asin, 0.0),
                parent_asin,
            ),
        )[:top_k]
        state.prior_recommendations.update(ranked)
        return ranked

    @staticmethod
    def _select_question(state: SessionState, turn: int) -> str | None:
        if turn >= 10:
            return None
        if "other" not in state.no_preference_attributes and state.question_counts["other"] < 3:
            return "other"
        for attribute in TYPED_QUESTION_ORDER:
            if (
                attribute not in state.no_preference_attributes
                and state.question_counts[attribute] < 2
            ):
                return attribute
        return None

    def respond(
        self,
        session_id: str,
        user_message: str,
        turn: int,
        top_k: int,
    ) -> dict:
        state = self._sessions.get(session_id)
        if state is None:
            raise RuntimeError("reset must be called before respond")
        evidence_changed = self._parse_message(state, user_message)
        ranked = self._rank(
            state,
            user_message,
            min(max(top_k, 0), 10),
            explore_unseen=not evidence_changed,
        )
        ask_attribute = self._select_question(state, turn)
        if ask_attribute:
            state.question_counts[ask_attribute] += 1
            message = QUESTION_TEXT[ask_attribute]
        else:
            message = "Here are the strongest matches for the preferences shared so far."
        return {
            "message": message,
            "ask_attribute": ask_attribute,
            "recommendations": [{"parent_asin": parent_asin} for parent_asin in ranked],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }
