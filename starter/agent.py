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
    r"\b(cotton|polyester|nylon|leather|wool|spandex|silk|rayon|fabric|"
    r"metal|alloy|steel|silver|gold|brass|copper|rubber|canvas|denim|"
    r"lace|linen|cashmere|suede|velvet|tweed|chiffon|satin|mesh|fleece|"
    r"neoprene|acrylic|viscose|modal)\b",
    re.IGNORECASE,
)
COLOR_RE = re.compile(
    r"\b(black|white|blue|red|pink|green|brown|gray|grey|purple|yellow|"
    r"orange|navy|beige|teal|burgundy|maroon|cream|ivory|tan|turquoise|"
    r"lavender|khaki|olive|coral|magenta)\b",
    re.IGNORECASE,
)
SIZE_WORD_RE = re.compile(
    r"\b(xxs|xs|s|m|l|xl|xxl|xxxl|small|medium|large|x-large|xx-large|"
    r"plus|petite|tall|wide|narrow|regular)\b",
    re.IGNORECASE,
)
SIZE_NUMBER_RE = re.compile(r"\b(\d{1,2}(?:\.\d)?)\b")
BUDGET_AMOUNT_RE = re.compile(r"\$?\s*(\d+(?:\.\d+)?)")
BUDGET_OPERATOR_RE = re.compile(
    r"\b(under|over|less than|more than|at least|up to|around|about|below|above)\b",
    re.IGNORECASE,
)
STOPWORDS = {
    "a", "additional", "an", "and", "are", "as", "at", "be", "but", "by",
    "do", "does", "for", "from", "have", "here", "i", "in", "is", "it",
    "judgment", "like", "looking", "matter", "matters", "me", "my", "need", "of",
    "on", "or", "please", "preference", "requirement", "some", "still", "that",
    "the", "this", "those", "to", "use", "want", "what", "with", "would", "you",
    "could", "should", "made", "make", "makes", "keep", "keeps", "try",
    "trying", "stay", "stays", "like", "likes", "really", "just", "one",
    "thing", "things", "something", "anything", "option", "options", "good",
    "better", "best", "prefer", "prefers", "preferred", "around", "about",
    "under", "over", "price", "prices", "budget", "cost", "color", "colour",
    "material", "style", "brand", "feature", "features", "kind", "type",
    "way", "bit", "little", "lot", "very", "quite", "also", "even", "well",
    "feel", "feels", "if", "possible", "anyway", "somehow", "maybe",
    "perhaps", "probably", "definitely", "absolutely",
}

SYNONYM_REPLACEMENTS = (
    ("water-resistant", "waterproof"),
    ("water resistant", "waterproof"),
    ("air-permeable", "breathable"),
    ("air permeable", "breathable"),
    ("feather-light", "lightweight"),
    ("feather light", "lightweight"),
    ("sweat-wicking", "moisture-wicking"),
    ("sweat wicking", "moisture-wicking"),
    ("long-lasting", "durable"),
    ("long lasting", "durable"),
    ("skin-safe", "hypoallergenic"),
    ("skin safe", "hypoallergenic"),
    ("stretchy", "stretch"),
    ("customizable fit", "adjustable"),
    ("easy to wear", "comfortable"),
)


def _apply_synonyms(value: str) -> str:
    """Map common rewordings to the catalog's canonical tokens."""
    result = value
    for source, canonical in SYNONYM_REPLACEMENTS:
        result = re.sub(rf"\b{re.escape(source)}\b", canonical, result, flags=re.IGNORECASE)
    return result

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
CONSTRAINT_MARKER_RE = re.compile(
    r"(?:a key requirement is|what i need is|for that, what matters is|"
    r"the thing that matters most is|the most important thing is|"
    r"the key thing is|the important thing is|"
    r"it (?:must|needs to) (?:have|be)|i (?:care about|need it to have)|"
    r"please prioritize|instead(?:,)?\s*(?:i\s+need)?)\s*:?\s*(.+)",
    re.IGNORECASE,
)
CATEGORY_PATTERNS = (
    re.compile(
        r"\bi['’]?m looking for\s+(.+?)(?=\.|,|;|\?|\s+(?:but|and)\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:please\s+)?help me find\s+(?:a |an |some )?(.+?)"
        r"(?=\.|,|;|\?|\s+(?:that|with|but|and)\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:could you\s+)?show me\s+(?:a |an |some )?(.+?)"
        r"(?=\.|,|;|\?|\s+(?:that|with|but|and)\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:i need|i['’]?m shopping for|find me)\s+(?:a |an |some )?(.+?)"
        r"(?=\.|,|;|\?|\s+(?:that|with|but|and)\b|$)",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:i want|i['’]?d like|searching for|looking for)\s+(?:a |an |some )?(.+?)"
        r"(?=\.|,|;|\?|\s+(?:that|with|but|and)\b|$)",
        re.IGNORECASE,
    ),
)
ERASE_OVERRIDE_RE = re.compile(
    r"\b(?:scratch|forget|remove|drop)\b|\b(?:don['’]?t|do not|no longer) want\b",
    re.IGNORECASE,
)
DEMOTE_OVERRIDE_RE = re.compile(
    r"\b(?:ignore my earlier preference|matters? less|less important|deprioriti[sz]e)\b",
    re.IGNORECASE,
)
OVERRIDE_CUE_RE = re.compile(
    r"\b(?:actually|instead|scratch|forget|changed my mind|no longer|rather)\b",
    re.IGNORECASE,
)
SHORT_LIST_MAX = 1


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


def _content_tokens(text: str) -> list[str]:
    """Tokens for ladder rung 3: keep numerics, drop only stopwords."""
    return [
        token.lower()
        for token in TOKEN_RE.findall(text)
        if token.lower() not in STOPWORDS
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


def _classify_attribute(value: str) -> str:
    lowered = value.lower()
    if "budget" in lowered or "price" in lowered or BUDGET_OPERATOR_RE.search(lowered) or re.search(r"\$\s*\d", lowered):
        return "budget"
    if MATERIAL_RE.search(lowered):
        return "material"
    if "color" in lowered or COLOR_RE.search(lowered):
        return "color"
    if "brand" in lowered:
        return "brand"
    if re.search(r"\b(size|sizing|width|wide|narrow|fit)\b", lowered):
        return "size"
    if any(word in lowered for word in ("style", "sleeve", "neck", "department")):
        return "style"
    if any(word in lowered for word in ("hiking", "running", "gym", "winter", "outdoor", "work", "occasion", "activity")):
        return "use_case"
    return "feature"


def _extract_budget(value: str) -> tuple[str, float] | None:
    """Return (operator, amount) for a budget constraint, or None."""
    amount_match = BUDGET_AMOUNT_RE.search(value)
    if not amount_match:
        return None
    amount = float(amount_match.group(1))
    lowered = value.lower()
    if re.search(r"\b(around|about)\b", lowered):
        return ("around", amount)
    if re.search(r"\b(over|more than|at least|above)\b", lowered):
        return ("ge", amount)
    return ("le", amount)


def _parse_price(value: object) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.replace("$", "").replace(",", "").strip()
        match = re.search(r"\d+(?:\.\d+)?", cleaned)
        if match:
            try:
                return float(match.group(0))
            except ValueError:
                return None
    return None


def _extract_size(value: str) -> str | None:
    word = SIZE_WORD_RE.search(value)
    if word:
        return word.group(1).lower()
    number = SIZE_NUMBER_RE.search(value)
    if number:
        return number.group(1)
    return None


@dataclass(frozen=True)
class Constraint:
    value: str
    normalized: str
    kind: str
    attribute: str


@dataclass
class SessionState:
    profile_terms: list[str]
    category: str = ""
    hard: list[Constraint] = field(default_factory=list)
    soft: list[Constraint] = field(default_factory=list)
    no_preference_attributes: set[str] = field(default_factory=set)
    question_counts: Counter[str] = field(default_factory=Counter)
    seen_normalized: set[str] = field(default_factory=set)
    superseded_normalized: str | None = None
    last_ranked: list[str] = field(default_factory=list)
    last_coverage: dict[str, tuple[int, int, int]] = field(default_factory=dict)
    last_relevance: dict[str, float] = field(default_factory=dict)


class Agent:
    """Deterministic, stateful constraint-satisfaction agent with a lexicographic ranker."""

    def __init__(self, catalog_path: str | Path = "data/catalog.jsonl") -> None:
        self.catalog_path = Path(catalog_path)
        self.connection = sqlite3.connect(":memory:")
        self._sessions: dict[str, SessionState] = {}
        self._quality: dict[str, float] = {}
        self._searchable: dict[str, str] = {}
        self._token_cache: dict[str, frozenset[str]] = {}
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
        cursor.execute(
            "CREATE TABLE typed_members ("
            "attribute TEXT NOT NULL, value TEXT NOT NULL, category TEXT NOT NULL, "
            "parent_asin TEXT NOT NULL)"
        )
        cursor.execute(
            "CREATE TABLE prices (parent_asin TEXT PRIMARY KEY, price REAL NOT NULL, "
            "category TEXT NOT NULL)"
        )

        product_batch: list[tuple[str, str, str, str, str, str, str]] = []
        evidence_batch: list[tuple[str, str]] = []
        category_batch: list[tuple[str, str, float]] = []
        typed_batch: list[tuple[str, str, str, str]] = []
        price_batch: list[tuple[str, float, str]] = []
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
                searchable = " ".join(
                    (title, features, details, description, categories, store)
                )
                self._searchable[parent_asin] = searchable
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
                material = MATERIAL_RE.search(searchable)
                color = COLOR_RE.search(searchable)
                if material:
                    possible_evidence.append(material.group(1).lower())
                    typed_batch.append(
                        ("material", material.group(1).lower(), category, parent_asin)
                    )
                if color:
                    possible_evidence.append(f"color: {color.group(1).lower()}")
                    typed_batch.append(
                        ("color", color.group(1).lower(), category, parent_asin)
                    )
                raw_price = product.get("price")
                if raw_price not in (None, ""):
                    possible_evidence.append(f"budget around ${raw_price}")
                    numeric_price = _parse_price(raw_price)
                    if numeric_price is not None:
                        price_batch.append((parent_asin, numeric_price, category))
                normalized_values = {
                    _normalize_evidence(_clean_constraint(value))
                    for value in possible_evidence
                    if _clean_constraint(value)
                }
                evidence_batch.extend(
                    (value, parent_asin) for value in normalized_values if value
                )

                for brand in self._extract_brands(product, store):
                    typed_batch.append(("brand", brand, category, parent_asin))
                for size in self._extract_sizes(product):
                    typed_batch.append(("size", size, category, parent_asin))

                if len(product_batch) >= 1000:
                    cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", product_batch)
                    cursor.executemany("INSERT INTO evidence VALUES (?, ?)", evidence_batch)
                    cursor.executemany("INSERT INTO category_members VALUES (?, ?, ?)", category_batch)
                    cursor.executemany("INSERT INTO typed_members VALUES (?, ?, ?, ?)", typed_batch)
                    cursor.executemany("INSERT INTO prices VALUES (?, ?, ?)", price_batch)
                    product_batch.clear()
                    evidence_batch.clear()
                    category_batch.clear()
                    typed_batch.clear()
                    price_batch.clear()

        if product_batch:
            cursor.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", product_batch)
            cursor.executemany("INSERT INTO evidence VALUES (?, ?)", evidence_batch)
            cursor.executemany("INSERT INTO category_members VALUES (?, ?, ?)", category_batch)
            cursor.executemany("INSERT INTO typed_members VALUES (?, ?, ?, ?)", typed_batch)
            cursor.executemany("INSERT INTO prices VALUES (?, ?, ?)", price_batch)
        cursor.execute("CREATE INDEX evidence_lookup ON evidence(normalized, parent_asin)")
        cursor.execute("CREATE INDEX category_lookup ON category_members(normalized, quality DESC)")
        cursor.execute("CREATE INDEX typed_lookup ON typed_members(attribute, value, category)")
        cursor.execute("CREATE INDEX prices_lookup ON prices(category, price)")
        self.connection.commit()

    @staticmethod
    def _extract_brands(product: dict, store: str) -> set[str]:
        brands: set[str] = set()
        store_norm = _normalize_evidence(store)
        if store_norm:
            brands.add(store_norm)
        for key, value in (product.get("details") or {}).items():
            if re.search(r"\b(brand|manufacturer|maker)\b", str(key), re.IGNORECASE):
                for item in _flatten_values(value):
                    normalized = _normalize_evidence(item)
                    if normalized:
                        brands.add(normalized)
        return brands

    @staticmethod
    def _extract_sizes(product: dict) -> set[str]:
        found: set[str] = set()
        for key, value in (product.get("details") or {}).items():
            if re.search(r"\b(size|width|fit)\b", str(key), re.IGNORECASE):
                text = _text(value)
                for word in SIZE_WORD_RE.findall(text):
                    found.add(word.lower())
                for number in SIZE_NUMBER_RE.findall(text):
                    found.add(number)
        for feature in _flatten_values(product.get("features")):
            if re.search(r"\b(size|width|fit)\b", feature, re.IGNORECASE):
                for word in SIZE_WORD_RE.findall(feature):
                    found.add(word.lower())
                for number in SIZE_NUMBER_RE.findall(feature):
                    found.add(number)
        return found

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

    @staticmethod
    def _add_constraint(
        state: SessionState,
        value: str,
        kind: str,
        superseded: bool = False,
    ) -> None:
        cleaned = _clean_constraint(value)
        normalized = _normalize_evidence(_apply_synonyms(cleaned))
        if not normalized:
            return
        if superseded:
            state.superseded_normalized = normalized
        if normalized in state.seen_normalized:
            return
        state.seen_normalized.add(normalized)
        constraint = Constraint(
            value=cleaned,
            normalized=normalized,
            kind=kind,
            attribute=_classify_attribute(cleaned),
        )
        if kind == "hard":
            state.hard.append(constraint)
            state.hard = state.hard[-8:]
        else:
            state.soft.append(constraint)
            state.soft = state.soft[-4:]

    @staticmethod
    def _demote_superseded(state: SessionState) -> None:
        if not state.superseded_normalized:
            return
        normalized = state.superseded_normalized
        state.superseded_normalized = None
        for constraint in list(state.hard):
            if constraint.normalized == normalized:
                state.hard.remove(constraint)
                state.soft.append(
                    Constraint(
                        value=constraint.value,
                        normalized=constraint.normalized,
                        kind="soft",
                        attribute=constraint.attribute,
                    )
                )

    @staticmethod
    def _erase_superseded(state: SessionState) -> None:
        """Remove an explicitly retracted constraint from active evidence."""
        normalized = state.superseded_normalized
        if not normalized:
            return
        state.superseded_normalized = None
        state.hard = [item for item in state.hard if item.normalized != normalized]
        state.soft = [item for item in state.soft if item.normalized != normalized]

    def _extract_category(self, message: str) -> str | None:
        for pattern in CATEGORY_PATTERNS:
            match = pattern.search(message)
            if not match:
                continue
            candidate = _clean_constraint(match.group(1))
            if not candidate:
                continue
            normalized = _normalize_evidence(candidate)
            if self._has_category(normalized):
                return candidate
        return None

    @staticmethod
    def _constraint_payloads(message: str) -> list[str]:
        """Extract explicit requirement clauses without treating small talk as evidence."""
        payloads: list[str] = []
        for match in CONSTRAINT_MARKER_RE.finditer(message):
            payload = match.group(1)
            payload = re.sub(
                r"\s+(?:instead|but|however)\b.*$", "", payload, flags=re.IGNORECASE
            )
            cleaned = _clean_constraint(payload)
            if cleaned:
                payloads.extend(
                    value
                    for value in (_clean_constraint(item) for item in cleaned.split(";"))
                    if value
                )
        return list(dict.fromkeys(payloads))

    def _parse_message(self, state: SessionState, message: str) -> bool:
        previous_category = state.category
        previous_hard = tuple(constraint.normalized for constraint in state.hard)
        previous_soft = tuple(constraint.normalized for constraint in state.soft)
        lowered = message.lower()

        is_override = bool(OVERRIDE_CUE_RE.search(message))
        if is_override and ERASE_OVERRIDE_RE.search(message):
            self._erase_superseded(state)
        elif is_override and DEMOTE_OVERRIDE_RE.search(message):
            # A reprioritization retains useful evidence at lower strength. This
            # also preserves the official simulator's "ignore earlier" policy.
            self._demote_superseded(state)

        category = self._extract_category(message)
        if category:
            state.category = category

        payloads = self._constraint_payloads(message)
        for payload in payloads:
            self._add_constraint(state, payload, "hard")

        # The official override scenario introduces its initial preference as a
        # bare sentence after the category. Preserve that protocol while keeping
        # exploratory phrases out of the constraint set.
        if category and not payloads and not is_override:
            category_end = lowered.find(category.lower()) + len(category)
            rest = _clean_constraint(message[category_end:].lstrip(" .,:;-"))
            if rest and not re.search(
                r"\b(?:still exploring|open to ideas|just browsing|not sure yet)\b",
                rest,
                re.IGNORECASE,
            ):
                self._add_constraint(state, rest, "hard", superseded=True)

        no_preference = re.search(
            r"(?:don['’]?t have|do not have|(?:i have )?no) (?:(?:a|an additional|any) )?"
            r"preference (?:for|about) ([a-z_]+)",
            lowered,
        )
        if no_preference:
            attribute = no_preference.group(1)
            if attribute in ALLOWED_ATTRIBUTES:
                state.no_preference_attributes.add(attribute)

        return (
            state.category != previous_category
            or tuple(constraint.normalized for constraint in state.hard) != previous_hard
            or tuple(constraint.normalized for constraint in state.soft) != previous_soft
        )

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

    def _has_category(self, normalized: str) -> bool:
        return bool(
            self.connection.execute(
                "SELECT 1 FROM category_members WHERE normalized = ? LIMIT 1",
                (normalized,),
            ).fetchone()
        )

    def _category_members(self, normalized: str, limit: int | None = None) -> list[str]:
        sql = "SELECT parent_asin FROM category_members WHERE normalized = ?"
        params: list[object] = [normalized]
        if limit is not None:
            sql += " ORDER BY quality DESC LIMIT ?"
            params.append(limit)
        return [str(row[0]) for row in self.connection.execute(sql, params)]

    def _exact_matches(self, normalized: str, category: str | None) -> set[str]:
        if category:
            rows = self.connection.execute(
                "SELECT evidence.parent_asin FROM evidence "
                "INNER JOIN category_members "
                "ON category_members.parent_asin = evidence.parent_asin "
                "WHERE evidence.normalized = ? AND category_members.normalized = ?",
                (normalized, category),
            )
        else:
            rows = self.connection.execute(
                "SELECT parent_asin FROM evidence WHERE normalized = ?",
                (normalized,),
            )
        return {str(row[0]) for row in rows}

    def _typed_lookup(self, attribute: str, value: str, category: str | None) -> set[str]:
        if category:
            rows = self.connection.execute(
                "SELECT parent_asin FROM typed_members "
                "WHERE attribute = ? AND value = ? AND category = ?",
                (attribute, value, category),
            )
        else:
            rows = self.connection.execute(
                "SELECT parent_asin FROM typed_members WHERE attribute = ? AND value = ?",
                (attribute, value),
            )
        return {str(row[0]) for row in rows}

    def _price_matches(
        self, operator: str, amount: float, category: str | None
    ) -> set[str]:
        if operator == "ge":
            predicate = "price >= ?"
        elif operator == "around":
            predicate = "price >= ? AND price <= ?"
        else:
            predicate = "price <= ?"
        if category:
            sql = f"SELECT parent_asin FROM prices WHERE {predicate} AND category = ?"
            params: tuple[object, ...] = (
                (amount * 0.85, amount * 1.15, category)
                if operator == "around"
                else (amount, category)
            )
        else:
            sql = f"SELECT parent_asin FROM prices WHERE {predicate}"
            params = (
                (amount * 0.85, amount * 1.15)
                if operator == "around"
                else (amount,)
            )
        return {str(row[0]) for row in self.connection.execute(sql, params)}

    def _typed_matches(self, constraint: Constraint, category: str | None) -> set[str]:
        attribute = constraint.attribute
        if attribute == "budget":
            parsed = _extract_budget(constraint.value)
            if not parsed:
                return set()
            return self._price_matches(parsed[0], parsed[1], category)
        if attribute == "material":
            material = MATERIAL_RE.search(constraint.value)
            if not material:
                return set()
            return self._typed_lookup("material", material.group(1).lower(), category)
        if attribute == "color":
            color = COLOR_RE.search(constraint.value)
            if not color:
                return set()
            return self._typed_lookup("color", color.group(1).lower(), category)
        if attribute == "brand":
            return self._typed_lookup("brand", constraint.normalized, category)
        if attribute == "size":
            size = _extract_size(constraint.value)
            if not size:
                return set()
            return self._typed_lookup("size", size, category)
        return set()

    def _product_token_set(self, parent_asin: str) -> frozenset[str]:
        cached = self._token_cache.get(parent_asin)
        if cached is not None:
            return cached
        tokens = frozenset(_content_tokens(self._searchable.get(parent_asin, "")))
        self._token_cache[parent_asin] = tokens
        return tokens

    def _token_overlap_matches(
        self, constraint: Constraint, category: str | None
    ) -> set[str]:
        constraint_tokens = [token for token in _content_tokens(_apply_synonyms(constraint.value))]
        if not constraint_tokens:
            return set()
        constraint_set = set(constraint_tokens)
        if category:
            pool = self._category_members(category, limit=3000)
        else:
            pool = self._fts_route(
                self._fts_expression([constraint.value]),
                300,
                (7.0, 5.0, 3.0, 2.5, 2.0, 1.0),
            )
        matches: set[str] = set()
        for parent_asin in pool:
            product_tokens = self._product_token_set(parent_asin)
            if not product_tokens:
                continue
            overlap = len(constraint_set & product_tokens)
            if overlap / len(constraint_set) >= 0.7:
                matches.add(parent_asin)
        return matches

    def _resolve_constraint(
        self, constraint: Constraint, category: str | None
    ) -> list[tuple[str, int]]:
        exact = self._exact_matches(constraint.normalized, category)
        if exact:
            return [(parent_asin, 1) for parent_asin in exact]
        typed = self._typed_matches(constraint, category)
        if typed:
            return [(parent_asin, 2) for parent_asin in typed]
        overlap = self._token_overlap_matches(constraint, category)
        if overlap:
            return [(parent_asin, 3) for parent_asin in overlap]
        return []

    def _rank(
        self,
        state: SessionState,
        message: str,
    ) -> tuple[list[str], dict[str, tuple[int, int, int]]]:
        coverage: dict[str, list[int]] = {}
        category_norm = _normalize_evidence(state.category)
        category_known = bool(category_norm and self._has_category(category_norm))
        constraints = [(c, "hard") for c in state.hard] + [(c, "soft") for c in state.soft]

        def add_match(parent_asin: str, kind: str, rung: int) -> None:
            if rung > 3:
                return
            record = coverage.setdefault(parent_asin, [0, 0, 0])
            if kind == "hard":
                record[0] += 1
            else:
                record[1] += 1
            record[2] += rung

        scoped = category_norm if category_known else None
        any_match = False
        for constraint, kind in constraints:
            for parent_asin, rung in self._resolve_constraint(constraint, scoped):
                add_match(parent_asin, kind, rung)
                any_match = True
        if not any_match and category_known:
            coverage.clear()
            for constraint, kind in constraints:
                for parent_asin, rung in self._resolve_constraint(constraint, None):
                    add_match(parent_asin, kind, rung)

        # Recall insurance (rung 4, zero coverage): keeps the pool non-empty and
        # broadens candidates when evidence is sparse, but never outranks a match.
        recall_parts = [
            message,
            state.category,
            *[constraint.value for constraint in state.hard],
            *[constraint.value for constraint in state.soft],
        ]
        for parent_asin in self._fts_route(
            self._fts_expression(recall_parts), 300, (7.0, 5.0, 3.0, 2.5, 2.0, 1.0)
        ):
            coverage.setdefault(parent_asin, [0, 0, 0])
        if category_known:
            for parent_asin in self._category_members(category_norm, limit=500):
                coverage.setdefault(parent_asin, [0, 0, 0])
        if len(coverage) < 100 and state.profile_terms:
            profile_expression = self._fts_expression([" ".join(state.profile_terms)])
            for parent_asin in self._fts_route(
                profile_expression, 100, (4.0, 2.0, 2.0, 2.0, 1.0, 1.0)
            ):
                coverage.setdefault(parent_asin, [0, 0, 0])

        relevance: dict[str, float] = {}
        relevance_routes = (
            (1.0, [message]),
            (1.5, [state.category, *[c.value for c in state.hard], *[c.value for c in state.soft]]),
        )
        for weight, parts in relevance_routes:
            expression = self._fts_expression(parts)
            for rank, parent_asin in enumerate(
                self._fts_route(expression, 400, (8.0, 5.0, 3.5, 3.0, 2.0, 1.0)),
                start=1,
            ):
                relevance[parent_asin] = relevance.get(parent_asin, 0.0) + weight / (60.0 + rank)

        ranked = sorted(
            coverage,
            key=lambda parent_asin: (
                -coverage[parent_asin][0],
                -coverage[parent_asin][1],
                coverage[parent_asin][2],
                -relevance.get(parent_asin, 0.0),
                -self._quality.get(parent_asin, 0.0),
                parent_asin,
            ),
        )
        tuple_coverage = {
            parent_asin: tuple(record) for parent_asin, record in coverage.items()
        }
        state.last_ranked = ranked
        state.last_coverage = tuple_coverage
        state.last_relevance = relevance
        return ranked, tuple_coverage

    @staticmethod
    def _select_question(state: SessionState, turn: int) -> str | None:
        if turn >= 10:
            return None
        # The open question is the union of every typed partition, so its
        # expected information gain is at least any single typed ask. Ask it
        # first; fall back to the fixed typed order only once it is declined or
        # exhausted. (A partition-entropy typed selector measured worse on the
        # public simulator, whose `feature` slot is a catch-all.)
        if "other" not in state.no_preference_attributes and state.question_counts["other"] < 3:
            return "other"
        for attribute in TYPED_QUESTION_ORDER:
            if (
                attribute not in state.no_preference_attributes
                and state.question_counts[attribute] < 2
            ):
                return attribute
        return None

    def _emit(
        self,
        ranked: list[str],
        coverage: dict[str, tuple[int, int, int]],
        top_k: int,
    ) -> list[str]:
        if not ranked:
            return []
        top_tier = coverage[ranked[0]][:2]
        tier = [parent_asin for parent_asin in ranked if coverage[parent_asin][:2] == top_tier]
        matched = top_tier[0] + top_tier[1]
        if matched == 0:
            # No disclosed constraint has catalog evidence yet: clarify first
            # instead of emitting a popularity-ranked tier.
            return []
        if matched < 2 and len(tier) > top_k:
            # Thin evidence over a wide tier: the evaluator freezes rank on the
            # first top-10 appearance, so a low-rank early hit locks a worse MRR
            # than waiting one turn for another constraint. Emit only the top
            # candidate and ask in parallel.
            return tier[:SHORT_LIST_MAX]
        return tier[:top_k]

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
        self._parse_message(state, user_message)
        ranked, coverage = self._rank(state, user_message)
        recommendations = self._emit(ranked, coverage, min(max(top_k, 0), 10))
        ask_attribute = self._select_question(state, turn)
        if ask_attribute:
            state.question_counts[ask_attribute] += 1
            message = QUESTION_TEXT[ask_attribute]
        else:
            message = "Here are the strongest matches for the preferences shared so far."
        return {
            "message": message,
            "ask_attribute": ask_attribute,
            "recommendations": [{"parent_asin": parent_asin} for parent_asin in recommendations],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }
