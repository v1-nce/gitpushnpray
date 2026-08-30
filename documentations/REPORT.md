# Shopping Copilot — Project Report

**TikTok TechJam 2026 · Track 4: AI Conversational Search and Recommendations**

## Overview

This submission is a **deterministic, offline conversational shopping agent** that
finds a hidden Amazon catalog product by `parent_asin` within at most 10 turns.
It replaces a weak stateless BM25 baseline with a constraint-satisfaction
pipeline: a multi-turn session state, a three-rung evidence-resolution ladder,
and a **lexicographic coverage ranker** that treats disclosed requirements as
satisfiable predicates rather than soft relevance signals.

No LLM, external API, credentials, network access, or third-party Python package
is required. The agent runs entirely in-memory from the standard library.

## Problem framing

The evaluator rewards three things:

```text
TechnicalScore = 0.50 * HitRate@10 + 0.30 * MRR + 0.20 * Efficiency
Efficiency     = clip((11 - MTTC) / 10, 0, 1)
```

A hit requires **exact `parent_asin` equality**; earlier turns and higher ranks
are better. The four pillars from the track brief are addressed as follows:

| Track pillar | How this submission addresses it |
|---|---|
| I. Intent routing & hybrid pipeline | Category-scoped multi-route retrieval (lexical + exact evidence + typed attribute maps), with an explicit high-precision track for hard constraints and a recall track for open browsing |
| II. Dialog strategy & state machine | Bounded session state with hard/soft constraint split, override *demotion* (slot rewrite), no-preference retirement, and proactive clarification |
| III. Self-evolution / context | Per-session context distillation (profile + resolved constraints) feeding the ranker; deterministic and privacy-safe, never shared across sessions |
| IV. Evaluation matrix | Reproducible train/val/test split **plus** an unseen-catalog + paraphrase attribution harness |

## Architecture

```text
catalog.jsonl (50,000 rows, read-only)
   -> build once per Agent: FTS5 index, exact-evidence map, category
      membership, typed attribute maps (material/color/size/brand/budget),
      price table, quality prior

reset(session_id, user_profile)  -> isolated session state
respond(session_id, message, turn, top_k)
   -> 1. parse message (typed slots, negations-ready, override, no-preference)
   -> 2. resolve each constraint through the ladder:
         rung 1  exact normalized string
         rung 2  typed value match (budget/material/color/brand/size)
         rung 3  token-overlap (>= 0.7 of content tokens)
         rung 4  BM25 recall insurance (never contributes coverage)
   -> 3. category-scoped candidate pool with unscoped fallback
   -> 4. rank lexicographically:
         -coverage_hard  >  -coverage_soft  >  +match_tier
         >  -relevance  >  -quality  >  +parent_asin
   -> 5. emit the top coverage tier; ask one clarification in parallel
```

The **core insight** is that constraint satisfaction is a lattice, not a
relevance score. A product that satisfies more hard constraints can never be
outranked by one that satisfies fewer, no matter how popular the latter is.
Relevance and quality only break ties *within* an equal-coverage tier.

## Model choice and cost

- **Model:** none. Retrieval and ranking are deterministic Python + SQLite FTS5.
- **Reported tokens:** `prompt_tokens = 0`, `completion_tokens = 0`.
- **API cost:** $0. **Network:** none. **Dependencies:** Python standard library.
- **Cold start:** ~33 s to build all indexes once per `Agent` instance.
- **Warm turn:** sub-second on verbatim dialogue; reworded constraints fall to
  the token-overlap scan and are slower (documented limitation).

## Evaluation scope (read before the numbers)

The official public evaluator is **verbatim**: the simulator reveals constraints
close to the catalog's own wording (`Material:alloy`, `budget around $79`).
That is the condition measured by the public-200 and unseen-400 rows.

The organizer's 800 private sessions are unknown. They are most likely the same
verbatim simulator, but could add natural-language paraphrasing. Therefore:

- the **unseen-400 verbatim** row is the honest generalization estimate for the  expected (verbatim) condition;
- the **typed / filler / structure reword** rows are a *robustness proxy* — they
  show how the agent degrades if dialogue is reworded, and are **not** a claim
  about the private set's distribution.

Do not present the paraphrase numbers as private-set performance.

## Results (honest, labeled)

| Evaluation | Hit@10 | MRR | MTTC | TechnicalScore |
|---|---:|---:|---:|---:|
| Released BM25 baseline | 0.125 | 0.068034 | 9.81 | 0.106710 |
| Public 200, full set (**overfit upper bound**) | 1.000 | 0.912048 | 2.06 | 0.952414 |
| Public 40 test split (**contaminated**) | 0.950 | 0.734861 | 2.825 | 0.858958 |
| **Unseen 400 targets, verbatim** | **0.975** | **0.7970** | 2.478 | **0.8971** |

The first two public rows were produced while inspecting those exact sessions,
so they are **not** unbiased. The unseen-400 row uses target products that never
appear in the 200 public sessions and is the best available generalization
proxy. The 800 organizer-private sessions remain the true holdout.

### Robustness attribution (unseen 200, verbatim vs perturbed)

| Mode | Hit@10 | MRR | Meaning |
|---|---:|---:|---|
| verbatim | 0.980 | 0.7757 | official simulator condition |
| typed reword | 0.915 | 0.7220 | reworded typed attributes |
| filler words | 0.920 | 0.7262 | hedged/natural phrasing |
| structure reword | 0.965 | 0.7393 | reworded sentence template |

The harness attributes each miss to `parser`, `retrieval`, or `ordering`. The
robustness pass recovered most of the paraphrase cliff at no verbatim cost; the
residual gap is an **information gap** (reworded constraints leave a wide,
indistinguishable tier), not a weight-tuning gap — a supervised 3-feature
reranker over 31k training pairs confirmed this.

## Evaluation discipline

- `data/splits/{train,val,test}.jsonl` — reproducible 60/20/20 scenario-stratified
  split (seed `20260830`). Tune on train, select on val, benchmark test once.
- `data/unseen/` — sessions for catalog targets outside the public 200.
- `scripts/bench.py` — orthogonal perturbation axes + per-session miss
  classification (this harness rejected five failed ideas during development).

## Limitations and future work

- The parser is no longer template-locked, but free-text negation is not yet
  fully modeled as a hard filter.
- The token-overlap rung is O(category pool); a lossless speedup needs a token
  inverted index.
- The residual paraphrase gap needs a semantic/dense route or richer typed
  features for `feature`/`style`/`use_case`.
- Cold-start memory/latency has not been benchmarked at scale.

## Reproduction

```bash
python3 -m unittest discover -s tests -v
python3 -m evaluator.local_evaluator                 # public 200 (overfit reference)
python3 -m scripts.make_splits                        # reproducible train/val/test
python3 -X utf8 -m scripts.bench_generalization \
    --dataset data/unseen/unseen.jsonl --mode verbatim   # unseen generalization
python3 -X utf8 -m scripts.bench \
    --dataset data/unseen/unseen_200.jsonl \
    --modes verbatim,typed,filler,structure             # robustness attribution
python3 -X utf8 -m scripts.demo --sample public_0001    # end-to-end demo transcript
```

## Team contributions

_To be completed by the team._

## Demo

An end-to-end transcript is generated by `scripts/demo.py` and written to
`demo_transcript.md`:

```bash
python3 -X utf8 -m scripts.demo --sample public_0001 --output demo_transcript.md
```

Link to the public YouTube walkthrough (to be added).
