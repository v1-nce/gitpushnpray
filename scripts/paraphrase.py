"""Deterministic, orthogonal perturbation of evaluator messages.

The public simulator reveals constraints close to verbatim ("Material:alloy",
"budget around $79"). That favours the agent's exact-string route and is the
main overfitting risk. This module rewrites messages along independent axes so
the benchmark can attribute any score drop to a specific failure mode:

- ``typed``    reword only typed attribute values (budget/material/color/size/
               brand/key:value), leaving free-text features verbatim. Tests the
               typed ladder rung.
- ``synonym``  replace catalog terms with plausible customer rewordings
               ("waterproof" -> "water-resistant"). Tests semantic recall.
- ``filler``   add non-matching filler words. Tests stopword/token-overlap
               robustness.
- ``structure`` reword the sentence template (category phrase, markers,
               override phrasing). Tests the parser.

Each axis is independently toggleable. ``intensity`` scales filler dilution.

Backward-compatible wrappers (``paraphrase_constraint``, ``paraphrase_message``,
``reword_message``) are kept for ``bench_generalization.py``.
"""

from __future__ import annotations

import re

MATERIAL_WORDS = (
    "cotton", "polyester", "nylon", "leather", "wool", "spandex",
    "silk", "rayon", "fabric",
)
COLOR_WORDS = (
    "black", "white", "blue", "red", "pink", "green", "brown", "gray",
    "grey", "purple", "yellow", "orange",
)
SIZE_WORDS = (
    "xxs", "xs", "s", "m", "l", "xl", "xxl", "xxxl", "small", "medium",
    "large", "plus", "petite", "tall", "wide", "narrow", "regular",
)

# (catalog_term, customer_reworded_term). These are deliberately NOT in the
# agent's synonym map, so they measure the semantic-recall gap honestly instead
# of being recovered by the agent's own normalization rules.
SYNONYMS = (
    ("waterproof", "water-repellent"),
    ("water resistant", "water-repellent"),
    ("breathable", "ventilated"),
    ("lightweight", "feather-weight"),
    ("moisture-wicking", "sweat-absorbing"),
    ("stretch", "elastic"),
    ("durable", "hard-wearing"),
    ("comfortable", "cozy"),
    ("hypoallergenic", "allergy-safe"),
    ("adjustable", "size-adjustable"),
    ("cotton", "all-cotton"),
    ("leather", "genuine-hide"),
    ("wool", "woolen"),
    ("silk", "silky"),
    ("denim", "jean-fabric"),
    ("suede", "brushed-leather"),
    ("fleece", "shearling"),
    ("linen", "flax-fabric"),
    ("warm", "insulated"),
    ("soft", "plush"),
    ("quick-dry", "fast-drying"),
    ("quick dry", "fast-drying"),
    ("machine-washable", "washer-safe"),
    ("machine washable", "washer-safe"),
    ("wide", "roomy"),
    ("narrow", "slim-cut"),
    ("black", "jet-black"),
    ("navy", "dark-blue"),
    ("red", "crimson"),
    ("pink", "rose"),
)

KEY_VALUE_RE = re.compile(r"^([a-z][a-z ]*):\s*(.+)$", re.IGNORECASE)
BUDGET_RE = re.compile(r"budget around \$?([\d.]+)", re.IGNORECASE)
COLOR_PREFIX_RE = re.compile(r"^color:\s*([a-z]+)$", re.IGNORECASE)

MARKERS = (
    "a key requirement is:",
    "what i need is:",
    "for that, what matters is:",
    "the thing that matters most is:",
    "the most important thing is:",
    "the key thing is:",
    "the important thing is:",
)


def typed_reword(value: str) -> str:
    """Reword only typed attribute values; leave free-text features verbatim."""
    cleaned = value.strip().rstrip(".")
    lowered = cleaned.lower()

    color = COLOR_PREFIX_RE.match(lowered)
    if color:
        return f"I'd like it in {color.group(1)}"

    budget = BUDGET_RE.search(lowered)
    if budget:
        return f"keep the price around ${budget.group(1)}"

    key_value = KEY_VALUE_RE.match(cleaned)
    if key_value:
        key = key_value.group(1).strip().lower()
        val = key_value.group(2).strip()
        if key in {"material", "fabric"}:
            return f"it should be made of {val}"
        if key in {"department", "style"}:
            return f"it should be a {val} style"
        if key in {"size", "width", "fit"}:
            return f"the {key} should be {val}"
        if key in {"brand", "manufacturer", "maker"}:
            return f"I'd prefer the {val} brand"
        return f"the {key} should be {val}"

    for material in MATERIAL_WORDS:
        if re.search(rf"\b{material}\b", lowered):
            return f"I'd prefer something made of {material}"

    for color_word in COLOR_WORDS:
        if re.search(rf"\b{color_word}\b", lowered):
            return f"a {color_word} option would be good"

    for size in SIZE_WORDS:
        if re.search(rf"\b{size}\b", lowered):
            return f"it needs to be a {size}"

    return value


def synonym_sub(value: str) -> str:
    """Replace catalog terms with customer rewordings."""
    result = value
    for source, target in SYNONYMS:
        result = re.sub(rf"\b{re.escape(source)}\b", target, result, flags=re.IGNORECASE)
    return result


def add_filler(value: str, intensity: float = 1.0) -> str:
    """Add non-matching filler words to dilute the token-overlap ratio."""
    cleaned = value.strip().rstrip(".")
    words = ("if", "possible", "as", "well", "anyway", "somehow")
    count = max(0, min(len(words), int(round(intensity))))
    extra = " ".join(words[:count])
    base = f"something with {cleaned}"
    return f"{base} {extra}".strip() if extra else base


def perturb_constraint(value: str, axes, intensity: float = 1.0) -> str:
    result = value
    if "synonym" in axes:
        result = synonym_sub(result)
    if "typed" in axes:
        result = typed_reword(result)
    if "filler" in axes:
        result = add_filler(result, intensity)
    return result


def perturb_payload(payload: str, axes, intensity: float = 1.0) -> str:
    return "; ".join(perturb_constraint(part, axes, intensity) for part in payload.split(";"))


def _perturb_payload_in_markers(message: str, axes, intensity: float) -> str:
    lowered = message.lower()
    for marker in MARKERS:
        position = lowered.find(marker)
        if position >= 0:
            head = message[: position + len(marker)]
            payload = message[position + len(marker):].strip().rstrip(".")
            return head + " " + perturb_payload(payload, axes, intensity)

    # Intent-override initial message: "I'm looking for {cat}. {old_value}"
    match = re.match(r"(.*?I['\u2019]?m looking for .+?\.)\s*(.+)", message, re.IGNORECASE)
    if match:
        return match.group(1) + " " + perturb_constraint(match.group(2), axes, intensity)
    return message


def _structure_reword(message: str, axes, intensity: float) -> str:
    lowered = message.lower()
    if "actually, ignore my earlier preference" in lowered:
        payload = message.split(":", 1)[-1].strip().rstrip(".")
        return "Scratch that, I changed my mind. Instead, " + perturb_constraint(
            payload, axes, intensity
        )
    if "i'm looking for" in lowered:
        match = re.search(r"i['\u2019]?m looking for (.+?)(?:\.|,)", message, re.IGNORECASE)
        if not match:
            return message
        category = match.group(1).strip()
        rest = message[match.end():].strip()
        if "a key requirement is:" in lowered:
            payload = message.split("a key requirement is:", 1)[-1].strip().rstrip(".")
            return (
                f"I need a {category}. The thing that matters most is: "
                + perturb_payload(payload, axes, intensity)
            )
        if "still exploring" in lowered:
            return f"I want a {category} but I'm still browsing around."
        return f"I want a {category}. " + perturb_constraint(rest, axes, intensity)
    if "for that, what matters is:" in lowered:
        return _perturb_payload_in_markers(message, axes, intensity)
    return message


def perturb_message(message: str, axes, intensity: float = 1.0) -> str:
    axes = set(axes)
    payload_axes = axes - {"structure"}
    if "structure" in axes:
        return _structure_reword(message, payload_axes, intensity)
    return _perturb_payload_in_markers(message, payload_axes, intensity)


# Backward-compatible wrappers for bench_generalization.py.
def paraphrase_constraint(value: str) -> str:
    return perturb_constraint(value, ("typed", "synonym", "filler"))


def paraphrase_payload(payload: str) -> str:
    return perturb_payload(payload, ("typed", "synonym", "filler"))


def paraphrase_message(message: str) -> str:
    return perturb_message(message, ("typed", "synonym", "filler"))


def reword_message(message: str) -> str:
    return perturb_message(message, ("typed", "synonym", "filler", "structure"))
