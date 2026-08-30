# Shopping Copilot Architecture

## Thesis

> **Constraint satisfaction is a lattice, not a relevance score.**

A customer who says "cotton, and under $40" is naming predicates a product either
satisfies or does not. The primary sort key is therefore **how many disclosed hard
constraints a product satisfies**; relevance and quality only break ties *within* an
equal-coverage tier.

## What `starter/agent.py` does

**Catalog prep (once per `Agent`)** — FTS5 text index, exact-evidence map, category
membership, typed attribute maps (material/color/size/brand/budget) and a price
table, plus a quality prior `rating/5 × log1p(rating_number)`.

**Session state (per `session_id`)** — category, hard/soft constraints, superseded
constraint, no-preference slots, question counts, prior recommendations. Isolated;
never shared across sessions.

**Parser** — extracts category and typed constraints without template markers; handles
override (`scratch that / changed my mind / instead`) and no-preference replies.

**Evidence ladder** — each constraint resolves through the first rung that matches:

| Rung | Method | Survives |
|---|---|---|
| 1 | exact normalized string | verbatim disclosure |
| 2 | typed value match (budget/material/color/brand/size) | complete rewording |
| 3 | token overlap ≥ 0.7 of synonym-normalized content tokens | reordering, mild drift |
| 4 | BM25 recall insurance | never contributes coverage |

**Ranking** — strict lexicographic keys, with category scoping (unscoped fallback):

```text
-coverage_hard > -coverage_soft > +match_tier > -relevance > -quality > +asin
```

`relevance` is rank-based FTS over the current message and the resolved state; it
breaks ties only within equal coverage.

**Emission gate** — no matched evidence → clarify only; one matched constraint over a
wide tier → emit the top candidate; otherwise emit the full top tier (≤ `top_k`).

**Dialogue** — ask `other` first (the union of typed partitions), then a fixed typed
order; retired slots are never re-asked.

## Key measured decision: override demotion

Track 4 §II says "slot erasure". The evaluator draws the retracted `old_value` and
the replacement `new_value` from the same target's intent card, so in all override
sessions the "retracted" preference is still true of the target. **Demoting** the
superseded value from hard to soft beats erasing it (MRR `0.864` vs `0.743`). We
deviate deliberately and report the number.

## Evaluation discipline

- `data/splits/` — reproducible 60/20/20 scenario-stratified split (seed `20260830`).
- `data/unseen/` — sessions for catalog targets absent from the 200 public sessions.
- `scripts/bench.py` — orthogonal perturbation axes (`typed`/`synonym`/`filler`/
  `structure`) and per-session miss classification (`parser`/`retrieval`/`ordering`).

## Honest results

| Evaluation | Hit@10 | MRR | TechnicalScore |
|---|---:|---:|---:|
| Released BM25 baseline | 0.125 | 0.068034 | 0.106710 |
| Public 200, full set (overfit) | 1.000 | 0.912048 | 0.952414 |
| **Unseen 400 targets, verbatim** | **0.975** | **0.7970** | **0.8971** |

The official simulator is verbatim; the paraphrase/reworded axes in `scripts/bench.py`
are a robustness proxy, not a claim about the private set.

## Implementation status

| Component | Status |
|---|---|
| Catalog prep, session state, parser, evidence ladder, category scoping, lexicographic ranker, override demotion, emission gate, boundary handling | Implemented |
| Information-gain clarifier | Partial (`other` first) |
| Negation as a hard filter | Not implemented |
| Dense / vector retrieval | Deferred — the residual paraphrase gap is semantic, not coverage |
| LLM parsing / reranking | Deferred — deterministic, zero tokens, zero cost |

## Limitations

- Public-set numbers are overfit; the unseen-400 verbatim row is the honest proxy.
- Paraphrase robustness is bounded by the lexical ladder (no semantic route).
- The token-overlap rung is O(category pool); a lossless speedup needs an inverted
  index.
- Cold start rebuilds all indexes (~33 s); peak memory is not yet benchmarked.

Experiment history and per-change ablations: [`EXPERIMENTS.md`](../results/EXPERIMENTS.md).
