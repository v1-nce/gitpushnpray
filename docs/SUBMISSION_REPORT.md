# Shopping Copilot Submission Report

## Project overview

This project implements a deterministic, offline conversational shopping agent for
the Track 4 exact-product retrieval task. Its central design principle is that explicit
shopping requirements form a constraint lattice: a product satisfying more hard
requirements must not be outranked by a product satisfying fewer requirements.

The agent builds in-memory SQLite FTS5, category, exact-evidence, typed-attribute, and
price indexes over the frozen 50,000-product catalog. Per-session state tracks hard and
soft constraints, declined attributes, question counts, and explicit preference
replacement. Ranking is lexicographic by hard coverage, soft coverage, evidence rung,
quality prior, and stable product ID.

## Tools and dependencies

- Python 3.10 or later
- Python standard library only
- SQLite FTS5 through Python's bundled `sqlite3`
- No external model, API, vector database, credentials, or network access

## Results

| Evaluation | Sessions | Hit Rate@10 | MRR | MTTC | TechnicalScore |
|---|---:|---:|---:|---:|---:|
| Official public development set | 200 | 1.000 | 0.912048 | 2.060 | 0.952414 |
| Catalog-disjoint paraphrase V1 | 200 | 0.790 | 0.519052 | 4.160 | 0.687516 |

The public set was repeatedly used during development and is not an unbiased holdout.
The synthetic shadow benchmark excludes public target products, changes customer
phrasing, and includes genuine conflicting overrides. It is a robustness diagnostic,
not an estimate of organizer-private performance.

## Cost, tokens, latency, and fallback

- Model and API cost: zero
- Prompt and completion tokens: zero
- Network requirement: none
- Offline fallback: the primary implementation is already offline
- Clean public evaluation: approximately 14 seconds on the latest development machine,
  including index construction and all 200 sessions

Cold-start peak memory and per-response p50/p95 latency must be captured on the final
submission machine before Devpost submission; the release checklist keeps this open.

## Reproduction

```bash
python3 -m unittest discover -s tests -v
python3 -X utf8 -m evaluator.local_evaluator --output results_public.json
python3 -X utf8 -m scripts.shadow_evaluator \
  --sample-count 200 \
  --seed 20260830 \
  --output results_shadow.json
```

## Limitations

- Public messages expose catalog-grounded strings close to verbatim, making the public
  score optimistic relative to natural paraphrases.
- Typed extraction covers material, color, size, budget, and brand but not every one of
  the catalog's 287 detail keys.
- The current clarification policy asks a broad `other` question before a bounded typed
  fallback; candidate-tier information gain remains future work.
- Category and constraint parsing is rule-based. New dialogue styles can still evade
  the patterns, although the shadow benchmark and paraphrase tests reduce this risk.
- Indexes are rebuilt for each process rather than persisted.

## Team contributions

Complete this section with each registered team member's name and concrete contribution
before submission. Do not submit generic or shared-only descriptions.
