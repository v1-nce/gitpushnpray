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
quality prior, and stable product ID. When a requirement arrives wrapped in the
customer's own words, the longest catalog phrase inside it is matched and merged with
the typed route, so specific evidence improves ordering without ever costing recall.

## Tools and dependencies

- Python 3.10 or later
- Python standard library only
- SQLite FTS5 through Python's bundled `sqlite3`
- No external model, API, vector database, credentials, or network access

## Results

| Evaluation | Sessions | Targets | Wording | Hit Rate@10 | MRR | MTTC | TechnicalScore |
|---|---:|---|---|---:|---:|---:|---:|
| Official public development set | 200 | seen | official | 1.000 | 0.899409 | 2.070 | 0.948423 |
| Unseen targets, official wording | 200 | unseen | official | 0.995 | 0.899560 | 2.125 | 0.944868 |
| Catalog-disjoint paraphrase V1 | 200 | unseen | rewritten | 0.945 | 0.848512 | 2.560 | 0.895854 |

The public set was repeatedly used during development and is not an unbiased holdout.
The two catalog-disjoint benchmarks differ in exactly one variable, which separates the
causes of the drop: unseen target products cost 0.004, and unfamiliar wording costs a
further 0.049.

Both catalog-disjoint benchmarks popularity-match their targets to the public set.
Official targets are real purchase records with a median of 7078 reviews against 12 for
the catalog, so uniform sampling produces a long-tail test set unlike anything the
organizer presents, and understates the scores by 0.06 to 0.10. Earlier revisions of
this report used uniform sampling.

The unseen-target benchmark is the closer private-set proxy, since it drives the
unmodified official dialogue policy against products excluded from the public set. It
assumes the organizer's private harness uses that same policy. The specification
reserves the right to add natural-language paraphrasing, which the paraphrase benchmark
bounds. Neither is a guarantee of organizer-private performance.

## Cost, tokens, latency, and fallback

- Model and API cost: zero
- Prompt and completion tokens: zero
- Network requirement: none
- Offline fallback: the primary implementation is already offline

Measured by `scripts.benchmark_runtime` on the development machine (Python 3.14.0,
Windows), artifact [`results/004_runtime_v1.json`](../results/004_runtime_v1.json):

| Quantity | Value |
|---|---:|
| Cold start (catalog load + index build), once per process | 20.2-25.7 s |
| Agent resident memory after build | ~301 MB |
| Per-response latency p50 | 26-64 ms |
| Per-response latency p95 | 73-204 ms |
| Per-response latency max | 136-445 ms |
| Full clean public evaluation, index build plus 200 sessions | 40.9 s |

Latency ranges span three runs and vary with machine load; memory and cold start are
stable across runs. About 220 MB of the resident footprint is SQLite's in-memory FTS5
index, which `tracemalloc` does not observe. These figures should be re-measured on the
final submission machine, which the release checklist tracks.

## Reproduction

```bash
python3 -m unittest discover -s tests -v
python3 -X utf8 -m evaluator.local_evaluator --output results_public.json
python3 -X utf8 -m scripts.unseen_target_evaluator --output results_unseen.json
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
- Indexes are rebuilt for each process rather than persisted, which costs 20-25 s of
  cold start and ~301 MB of resident memory in every scoring process.

## Team contributions

Complete this section with each registered team member's name and concrete contribution
before submission. Do not submit generic or shared-only descriptions.
