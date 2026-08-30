# Public Experiment Log

This log records development results on the released 200-session public set.
It is not evidence of performance on the organizer's 800 private sessions.

## Protocol

- Dataset: `data/public_set.jsonl` (200 sessions)
- Catalog: frozen 50,000-row `data/catalog.jsonl`
- Evaluator: unmodified `evaluator/local_evaluator.py`
- Runtime: Python 3.12.13 on the development Windows machine
- Dependencies: Python standard library only
- Model/API usage: none
- Reported prompt/completion tokens: zero
- Network and credential requirement: none

The public set was used repeatedly for diagnosis and tuning. It must therefore
be treated as development data rather than an untouched holdout.

## Results

| Version | Main change | Hit Rate@10 | MRR | MTTC | TechnicalScore | Artifact |
|---|---|---:|---:|---:|---:|---|
| Released baseline | Stateless single-query BM25 | 0.125 | 0.068034 | 9.810 | 0.106710 | [000](../docs/baseline_results.json) |
| Stateful evidence V1 | Accumulated state, exact evidence, multi-route sparse retrieval | 0.950 | 0.663776 | 2.595 | 0.842233 | — |
| Parser and exploration | Correct no-preference parsing and unseen-candidate exploration | 0.955 | 0.657484 | 2.585 | 0.843045 | — |
| Category-scoped evidence | Prevent generic attributes from dominating across categories | 0.995 | 0.694296 | 2.205 | 0.881689 | — |
| Current | Repeat a productive typed clarification once | **1.000** | **0.699296** | **2.175** | **0.886289** | [001](001_stateful_hybrid.json) |
| Lexicographic V1 | Coverage-lattice ranker, hard/soft demotion, evidence ladder, confidence gate | **1.000** | **0.912048** | **2.06** | **0.952414** | [002](002_lexicographic_v1.json) |
| Embedded phrase V1 | Match the longest catalog phrase inside a payload; merge with the typed route | 1.000 | 0.899409 | 2.070 | 0.948423 | [006](006_embedded_phrase_v1.json) |

### Catalog-disjoint robustness benchmark

The synthetic shadow benchmark is deliberately reported separately from the official
public evaluator. It excludes every public target product, keeps the official scenario
mix, varies dialogue wrappers, uses deterministic surface paraphrases, and includes
conflicting overrides that require true erasure.

| Version | Targets | Hit Rate@10 | MRR | MTTC | TechnicalScore | Artifact |
|---|---:|---:|---:|---:|---:|---|
| Paraphrase V1, initial wrapper tokens | 200 | 0.735 | 0.499442 | 4.590 | 0.645533 | scratch run |
| Paraphrase V1, conversational wrapper stopword | 200 | 0.790 | 0.519052 | 4.160 | 0.687516 | [003](003_shadow_paraphrase_v1.json) |
| Paraphrase V1, embedded catalog phrases | 200 | **0.890** | **0.649177** | **3.255** | **0.794653** | [007](007_embedded_phrase_shadow.json) |

The single measured change treats the wrapper word `like` as dialogue rather than
product evidence. The +0.055 Hit Rate gain illustrates why parser/retrieval evaluation
must extend beyond copied catalog strings. This benchmark is synthetic and is not a
claim about organizer-private performance.

### Target sampling correction: both generalization benchmarks were measuring the wrong catalog

The unseen-target and paraphrase benchmarks both sampled targets uniformly from the
50,000-product catalog. Official targets are real purchase records drawn from the
Clothing 5-core split, and their popularity profile is nothing like the catalog's:

| Target pool | Median review count | Share with fewer than 5 reviews |
|---|---:|---:|
| Official public targets | 7078 | 1.0% |
| Whole catalog (the old sampling pool) | 12 | 30.5% |

Uniform sampling therefore built long-tail test sets, and any ranking signal correlated
with popularity was judged against a distribution the organizer will never present. Both
benchmarks now draw one unseen product per public target from the same log2 review-count
band; `--uniform-targets` reproduces the old pool.

The correction moves the numbers a long way, and in the optimistic direction:

| Benchmark | Uniform sampling (superseded) | Popularity-matched | Artifact |
|---|---:|---:|---|
| Unseen targets, official wording | 0.880358 | **0.944868** | [008](008_unseen_popularity_matched.json) |
| Paraphrased wording | 0.794653 | **0.895854** | [009](009_shadow_popularity_matched.json) |

The decomposition published earlier was wrong in proportion as well as magnitude. Against
the corrected pools, unseen target products cost **0.004** (public `0.948423` to
`0.944868`), not 0.072, and unfamiliar wording costs **0.049** (to `0.895854`), not 0.192.
The agent transfers to unseen products almost perfectly; essentially all remaining
generalization risk is in phrasing.

This was found by accident. The coverage-precision tie-break below improved both
generalization benchmarks while destroying public MRR, an asymmetry too large to be
tuning noise, and investigating it exposed the sampling flaw rather than a property of
the change.

Two consequences for how these benchmarks are read:

1. A number from a self-authored benchmark is only as good as its sampling. Both of
   these were built carefully in every respect except the one that mattered.
2. The public set, for all that it is saturated and tuned on, is the only benchmark
   whose target distribution is known to be correct. Treat a large public regression as
   evidence against a change even when the generalization benchmarks approve of it.

### Sealed-seed check on the unseen-target benchmark

The agent has no fitted parameters, so the unseen-target benchmark cannot be
contaminated by training. It can still be consumed by selection: roughly five
accept/reject decisions were taken with its numbers in view (adopting embedded phrase
matching, choosing merge over replace, and rejecting IDF weighting, tier-splitting
clarification, and the coverage-precision tie-break). Every one used seed `20260830`.

Two seeds that informed no decision were therefore run as a sealed check:

| Seed | Informed a decision | Hit Rate@10 | MRR | TechnicalScore |
|---|---|---:|---:|---:|
| `20260830` | yes, all of them | 0.995 | 0.899560 | 0.944868 |
| `31337` | no | 0.975 | 0.861603 | 0.918981 |
| `987654` | no | 0.995 | 0.890262 | 0.942379 |

One sealed seed reproduces the tuning seed almost exactly; the other is 0.026 lower.
The tuning seed is the highest of the three, which is a mild warning, though at this
spread and with three samples it is consistent with ordinary sampling variation rather
than measurable selection damage. The published estimate is a range, 0.92 to 0.945,
centred near 0.935.

Most of the decisions above were rejections driven by the *public* number rather than
acceptances driven by this one, which limits the exposure. The coverage-precision
tie-break is the clearest case: both generalization benchmarks approved it and it was
rejected on the public regression.

Standing discipline: tune against `20260830`, and keep a seed sealed for a final check
before submission. A seed loses its value the moment a decision is made against it.

### Unseen-target benchmark: separating the two causes of the shadow drop

The paraphrase benchmark changes the target product **and** the customer's wording,
so its 0.688 cannot attribute the drop to either. `scripts.unseen_target_evaluator`
changes only the target: every message is produced by the unmodified official
simulator, against products excluded from the public set.

| Benchmark | Targets | Wording | Hit Rate@10 | MRR | MTTC | TechnicalScore | Artifact |
|---|---|---|---:|---:|---:|---:|---|
| Official public set | seen | official | 1.000 | 0.912048 | 2.060 | 0.952414 | [002](002_lexicographic_v1.json) |
| Unseen targets, seed `20260830` | unseen | official | 0.965 | 0.760861 | 2.520 | **0.880358** | [005](005_unseen_official_v1.json) |
| Paraphrase V1, seed `20260830` | unseen | rewritten | 0.790 | 0.519052 | 4.160 | 0.687516 | [003](003_shadow_paraphrase_v1.json) |

Decomposition of the 0.952 to 0.688 gap:

- unseen target products cost **-0.072** (0.952 to 0.880)
- unfamiliar wording costs a further **-0.192** (0.880 to 0.688)

Wording dominates by roughly 2.7x. Three seeds of the unseen-target benchmark give
0.880358, 0.890283, and 0.894993, so the estimate is stable to about 0.008.

If the organizer's private harness uses the shipped dialogue policy, 005 is the
relevant estimate and the expected private score is near **0.88**. If their phrasing
differs from the shipped templates, 003 is the relevant estimate. Closing that gap
is the highest-value remaining work, and the parser is where it lives: constraints
are extracted only behind the fixed markers in `CONSTRAINT_MARKER_RE`, so a sentence
carrying the same requirement in different words yields no evidence at all.

Note that MRR falls from 0.912 to 0.761 on unseen targets while Hit Rate barely moves.
The ranker's tie-breaking among equally-covered products is the component most fitted
to the public set.

### Embedded catalog phrases: trading a little public MRR for paraphrase robustness

Diagnosis first. Every one of the 47 paraphrase-benchmark misses classified as
`ranking_too_low`: no parsing failure, no recall failure, no wrong category. The
evidence was parsed, resolved, and reached the target, which sat at a rank such as
58 of a 1346-product pool. A free-text extraction parser would have fixed none of
them.

The rung histogram located the real cause. Across all accumulated constraints only
10 resolved at rung 1 (exact catalog phrase) against 97 typed and 94 token-overlap.
Paraphrasing does not remove evidence, it *coarsens* it: `I would like 100% Cotton`
fails whole-payload equality and falls back to typed `material=cotton`, which matches
every cotton shirt instead of the few that are 100% cotton. Rank collapses because
the surviving evidence no longer discriminates.

The change matches the longest catalog phrase *contained* in a payload when whole
payload equality fails. Every phrase tried must already exist in the catalog-derived
evidence table, so no evidence is invented.

Two variants were measured. Both leave the unseen-target benchmark byte-identical at
0.880358, because verbatim constraints already resolve at rung 1 and never reach the
new code path.

| Variant | Public | Paraphrase shadow | Unseen targets |
|---|---:|---:|---:|
| Baseline (002) | 0.952414 | 0.687516 | 0.880358 |
| A: embedded replaces the typed route | 0.943267 | **0.824353** | 0.880358 |
| B: embedded merged with the typed route (**adopted**) | **0.948423** | 0.794653 | 0.880358 |

The variant table below was measured on the uniform pool and its shadow column is
therefore superseded; re-measured against the popularity-matched pools, the adopted
change costs 0.004 public and 0.002 unseen and gains **0.047** on paraphrased wording
(parent `0.849141` to `0.895854`, Hit Rate 0.920 to 0.945, MRR 0.748470 to 0.848512).
The change remains justified, but the headline gain is 0.047 rather than the 0.107 first
reported.

Variant A scores higher on the shadow benchmark but drops public Hit Rate@10 from
1.000 to 0.990. Replaying `public_0014` showed why: the narrower exact set replaced
the broader typed set and collapsed the candidate pool to two products, neither of
them the target. Variant B keeps both routes and records the stronger rung per
product, so the merge can only add candidates, never remove one. That invariant, not
a tuned constant, is why B was adopted; it recovers 0.107 of A's 0.137 gain while
restoring Hit Rate@10 to 1.000.

A minimum phrase length of three tokens was also tried: it cost the shadow benchmark
0.030 (0.824 to 0.765 under variant A) and recovered no public score. Reverted.

The cost is 0.013 of public MRR (0.912048 to 0.899409). Public MRR is the metric most
fitted to the development set, and the same change is worth 0.107 on unfamiliar
wording, so the trade was taken deliberately. Per-response latency and resident memory
are unchanged within run-to-run variance.

### Runtime, memory, and latency

Measured by `scripts.benchmark_runtime` on the development machine (Python 3.14.0,
Windows). This experiment changes no agent behaviour; it exists because the organizer
may impose CPU, memory, and timeout limits.

| Quantity | Value | Note |
|---|---:|---|
| Cold start (catalog load + index build) | 20.2–25.7 s | Once per process |
| Agent resident memory after build | ~301 MB | Excludes the simulator's own catalog copy |
| Python heap peak (`tracemalloc`) | 79.3 MB | The other ~220 MB is SQLite's C-level FTS5 index |
| Per-response latency p50 | 26–64 ms | 412 responses over 200 sessions |
| Per-response latency p95 | 73–204 ms | Range across three runs |
| Per-response latency max | 136–445 ms | Worst single turn observed |
| Full clean public evaluation | 40.9 s | Index build plus all 200 sessions |

Latency varies roughly 2.5x with machine load while memory and cold start stay stable,
so the p95 and max columns are reported as ranges over three runs rather than as single
values. The retained artifact [004](004_runtime_v1.json) records the most conservative
run. `tracemalloc` roughly triples the measured index-build time, so heap tracing is
opt-in behind `--trace-heap` and the script marks such a run's timing invalid.

The full-run figure supersedes an earlier claim of approximately 14 seconds, which no
measurement on this machine reproduces.

Current scenario Hit Rate@10 is 1.0 for Buying, Browsing, Intent Override, and
Boundary. The complete output was byte-identical across two clean evaluator
processes (SHA-256 `7A3A43BF490FE4D985C11747A2B5F4BEC6058D84BCB429B46720A088574EC05D`).
One complete run took approximately 33.2 seconds including index construction
and all conversations. Eight focused unit tests pass.

Raw evaluator outputs are stored in this folder (`results/`) and named
`NNN_slug.json`; the convention and lineage rules are documented in
[`README.md`](README.md). The table above links each retained experiment to its
artifact.

## What produced the gain

1. Retaining category and disclosed constraints across turns fixed the
   starter's repeated stateless queries.
2. Mapping catalog-grounded evidence back to products recovered candidates
   when a constraint appeared close to verbatim.
3. Restricting exact evidence to the resolved category prevented generic
   values such as `Imported` from favoring unrelated products.
4. A small penalty for previously recommended candidates broadened exploration
   when a turn supplied no new evidence.
5. Boundary handling retires declined attributes, while a productive typed
   question can repeat once to obtain additional constraints of the same type.

## Limitations and overfitting risk

- Every public session was available during development; the final public score
  is descriptive, not an unbiased estimate.
- The official simulator frequently reveals catalog strings close to verbatim.
  Exact-evidence matching may degrade when a person paraphrases the same idea.
- The parser recognizes the evaluator's standard message markers more reliably
  than arbitrary natural conversation.
- Asking `other` is unusually productive in the public simulator and is less
  specific than a real shopping assistant should be.
- Hit Rate only requires the target to appear anywhere in Top 10. MRR below 1.0
  shows that the exact target is not consistently ranked first.
- Indexes are rebuilt for each clean process. Cold start and peak memory are now
  measured (see above); index persistence remains future work.

## Reproduction

```bash
python3 -m unittest discover -s tests -v
python3 -X utf8 -m evaluator.local_evaluator --output results/NNN_slug.json
python3 -X utf8 -m scripts.diagnose_sessions public_0001 --top-n 10
python3 -X utf8 -m scripts.benchmark_runtime --output results/NNN_slug.json
python3 -X utf8 -m scripts.chat_agent --random --seed 42
```

## Recording experiments

Write each evaluator run to `results/NNN_slug.json` rather than the default
root `results.json` (see [`README.md`](README.md)), then append one linked row
to the table above **and** the same pointer row to the lineage table in
[`README.md`](README.md). Retained artifacts are the authoritative record; the
table here is the human-readable index.

## Reverted experiments (lineage dead ends)

- **Coverage-precision tie-break** (parent 006, reverted, but productive): replaced the
  popularity prior with the fraction of each product's description accounted for by the
  disclosed requirements, so a plain product matching narrowly would outrank a
  feature-dense one satisfying the same requirements incidentally.

  | Benchmark | Parent | Coverage precision |
  |---|---:|---:|
  | Public | 0.948423 | 0.885062 |
  | Unseen targets (uniform pool) | 0.880358 | 0.892468 |
  | Paraphrase shadow (uniform pool) | 0.794653 | 0.829236 |

  Both generalization benchmarks improved while public MRR collapsed from `0.899409` to
  `0.725208`. That asymmetry was the useful part: it was far too large for tuning noise,
  and chasing it exposed the target sampling flaw described above rather than anything
  about the change itself.

  With the cause understood the result reads plainly. Official targets are real purchase
  records and are overwhelmingly popular, so the popularity prior is a genuinely
  informative signal for them; the uniform pools were long-tail, where it is noise.
  Demoting it therefore looked good on two broken benchmarks and bad on the one whose
  target distribution was right. Rejected on those grounds rather than re-measured,
  because the public regression is the trustworthy measurement here.

  Worth revisiting only as a tie-break *after* the quality prior rather than instead of
  it, where it could order products that popularity leaves tied without discarding a
  signal that demonstrably works. No artifact retained.

- **Tier-splitting clarification** (parent 006, reverted): kept the `other`-first
  ask, then chose the typed fallback attribute whose values partition the currently
  tied top group most evenly, by entropy over per-product indexed values. Intended to
  supply the one thing a tie needs and reweighting cannot give it: a fact the customer
  has not stated.

  | Benchmark | Parent | Tier-splitting |
  |---|---:|---:|
  | Public | 0.948423 | 0.946623 |
  | Unseen targets | 0.880358 | 0.880544 |
  | Paraphrase shadow | 0.794653 | 0.788366 |

  The targeted effect appeared and was too small to pay for itself. Unseen-target MRR
  rose `0.760861` to `0.764813`, but MTTC worsened on all three benchmarks (2.07 to
  2.16, 2.52 to 2.57, 3.255 to 3.41) and the net was negative twice.

  The cause is a property of the simulator rather than of the idea. A question's value
  here is dominated by how much evidence the answer carries, not by how well the
  attribute divides the tier. `other` is answered with up to two constraints of any
  type, while a typed question returns only constraints of that type and otherwise
  spends the turn on "no preference". Choosing an attribute for its split power
  therefore often selects one the customer has nothing to say about, and the turn is
  wasted.

  This is the second information-gain question selector to fail for the same reason,
  after the partition-entropy clarifier below. Treat the pairing of `other`-first with
  a fixed typed fallback as the measured local optimum for this dialogue policy, and
  attack the MRR ceiling from the ranking side instead. No artifact retained.

- **Constraint specificity weighting / IDF** (parent 006, reverted): weighted each
  satisfied requirement by its rarity, `log(catalog_size / (1 + match_count))`,
  accumulated per product and inserted as a tie-break between the evidence rung and
  the quality prior. The intent was to stop the popularity prior from settling ties
  in favour of bestsellers over the customer's actual target.

  Measured flat. Public `0.948423` and unseen targets `0.880358` were byte-identical
  to the parent, MRR unchanged to six decimals; the paraphrase shadow moved
  `0.794653` to `0.795653`, one session shifting rank on a single seed.

  The reason is structural rather than a tuning problem, and it was predicted before
  the run. Rarity can only separate products that satisfy *different* requirements of
  the same count. The surviving ties are products satisfying the *identical*
  requirement set, drawn from one category, so every candidate receives exactly the
  same weight sum and the ordering is unchanged. Breaking those ties needs evidence
  the agent does not currently hold, not a reweighting of the evidence it does.

  Reverted rather than kept: a fourth sort key and a restructured accumulator are not
  justified by +0.001 on a self-authored benchmark. No artifact retained.

- **Partition-entropy typed clarifier** (parent 002, reverted): chose the typed
  attribute with the most distinct values over the current tier. On the public
  simulator `feature` is the evaluator's catch-all slot, so it picked narrower
  slots and regressed boundary MRR `0.910` to `0.785` (overall score `0.952` to
  `0.949`). Reverted to `other`-first then fixed typed order; no artifact
  retained.

## Next experiments

1. Done, see [005](005_unseen_official_v1.json): protocol-compatible sessions for
   catalog targets outside the 200 public targets.
2. Expand the paraphrase benchmark with independently authored semantic rewrites,
   negative constraints, and category overrides.
3. Accumulate materials, colors, brands, sizes, budgets, negations, and
   corrections from arbitrary customer sentences rather than fixed templates.
4. Compare the fixed question policy with category-grounded candidate entropy
   or expected information gain.
5. Improve ordering among products that share all disclosed evidence, targeting
   MRR without sacrificing Hit Rate or MTTC. Note that the corrected benchmarks put
   unseen-target MRR at `0.899560`, level with the public set, so this headroom is
   far smaller than the uniform-pool measurement suggested. Three approaches are now
   excluded.
   Reweighting the evidence cannot work (reverted IDF experiment): tied products
   satisfy the identical requirement set and carry identical weight. Acquiring
   more evidence by question selection cannot pay for itself either (reverted
   tier-splitting experiment): the turn it costs exceeds the rank it buys.
   Coverage precision, the per-product discriminator, has now been tried as a
   replacement for the popularity prior and rejected: popularity is real signal for
   targets that are real purchase records. It remains untried as a tie-break placed
   after the quality prior instead of before it.
6. Reduce the 20-25 s cold start and ~301 MB resident footprint, most plausibly by
   persisting the SQLite index instead of rebuilding it per process, before any
   embedding or LLM reranker adds to either budget.
