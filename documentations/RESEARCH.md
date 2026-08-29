# Track 4 Research and Experiment Guide

This document turns verified competition facts and relevant information-retrieval
research into an implementation and experimentation guide for the Shopping
Copilot. It is not a second competition specification and it does not establish
that any proposed method will improve the private score.

**Read [`AGENTS.md`](../AGENTS.md) first.** When sources disagree, preserve the
machine-readable [API contract](../docs/agent_api_contract.json) and public
[evaluator behavior](../evaluator/local_evaluator.py), then flag the discrepancy.
The primary local sources are:

- [`TRACK_4.md`](TRACK_4.md): original track brief;
- [`competition_specification.md`](../docs/competition_specification.md): task,
  protocol, scenarios, and metrics;
- [`agent_api_contract.json`](../docs/agent_api_contract.json): exact I/O schema;
- [`evaluation_config.json`](../docs/evaluation_config.json): scoring constants;
- [`submission_rules.md`](../docs/submission_rules.md): packaging and runtime rules;
- [`local_evaluator.py`](../evaluator/local_evaluator.py): public simulator/scorer;
- [`starter/agent.py`](../starter/agent.py): current weak baseline.

## 1. Executive strategy

Build the smallest measurable, catalog-grounded system that improves exact-ID
retrieval:

1. Parse each message into typed, session-local constraint updates.
2. Retrieve independently from current-turn text and resolved active intent.
3. Combine field-aware lexical, structured, and typo-tolerant candidate routes.
4. Preserve candidate recall, then rerank with hard-constraint coverage and
   stable tie-breaking.
5. Recommend on every turn; ask one useful clarification in parallel when its
   likely value exceeds the cost of another turn.
6. Add dense retrieval, learned reranking, or an LLM only after an ablation
   identifies a failure those components can fix.
7. Promote changes on official metrics and paired held-out evidence, not on
   architectural novelty.

The most impressive submission is not the system with the most components. It
is the one with a defensible score gain, robust override and boundary behavior,
low offline latency, deterministic fallback, clear ablations, and a polished
multi-turn demonstration.

## 2. Competition facts and score economics

### Scored behavior

- A hit requires exact `parent_asin` equality. Semantically similar substitutes
  and sibling products receive no credit.
- Only the first 10 unique, catalog-valid recommendations are scored. An
  optional per-item `score` is ignored.
- A session ends at the first hit or after turn 10. A miss contributes turn 11
  to MTTC.
- The scenario mix is Buying 40%, Browsing 40%, Intent Override 15%, and
  Boundary 5%. The evaluator also reports each scenario separately.
- Intent Override cannot score before the replacement intent is sent.
- `ask_attribute`, not question prose, controls what the simulator reveals.
- Recommendations are scored before the next customer reply is generated, so
  clarification should normally accompany—not replace—a ranked list.
- Exceptions, malformed output, and invalid responses can become misses.
- Token use and latency are feasibility measures, not core-score terms.

### Required response invariants

`message` must be a string. `ask_attribute` must be one of `category`,
`material`, `color`, `size`, `style`, `brand`, `budget`, `feature`, `use_case`,
`other`, or `None`. `recommendations` must contain catalog IDs in rank order.
When `usage` is returned, both token counts must be non-negative integers. The
contract fixes `turn` to 1–10 and `top_k` to 10.

### Objective and marginal value

```text
Efficiency = clip((11 - MTTC) / 10, 0, 1)
TechnicalScore = 0.50 * HitRate@10 + 0.30 * MRR + 0.20 * Efficiency
```

Holding other metrics fixed:

- +0.01 HitRate adds 0.005 TechnicalScore;
- +0.01 MRR adds 0.003;
- +0.01 Efficiency adds 0.002;
- reducing aggregate MTTC by 0.1 adds 0.002 while Efficiency is unclipped.

Turning one miss into a hit at rank `r`, turn `t`, in an `N`-session evaluation
adds approximately

```text
(0.50 + 0.30 / r + 0.02 * (11 - t)) / N
```

because it improves all three terms. This makes candidate recall the first
priority, rank quality the second, and early conversion the third. It does not
justify returning weak guesses: ranking ten valid candidates and asking a
question can happen in the same response.

## 3. What the public evaluator actually does

These are public-simulator observations, not universal facts about shoppers.
Do not hard-code public targets, sample order, IDs, exact simulator sentences,
or labels around them.

- Buying starts with a coarse category and the first hard constraint.
- Browsing and Boundary start with a coarse category and exploratory language.
- A typed `ask_attribute` reveals undisclosed constraints classified into that
  slot when available. `other` is a broad fallback in the public simulator.
- No `ask_attribute` yields a prompt asking the agent to request a specific
  attribute; it does not reveal another constraint.
- Boundary can answer that it has no preference for the requested attribute.
  Store that result and do not ask the same unavailable slot again.
- Intent Override sends explicit replacement language on turn 3 or 4. Remove
  the superseded preference and rerun retrieval; do not accumulate both values.
- Public samples without materialized intent cards are expanded inside the
  evaluator from the target's catalog metadata. This is evaluator-only state
  and must never be accessed by runtime agent code.

Use these facts to test protocol behavior, not to imitate one exact simulator.
A private-safe policy understands replacement and no-preference language in
multiple phrasings and chooses questions from current catalog uncertainty.

## 4. Current baseline and its failure modes

The checked-in SQLite FTS5 baseline reports:

| Metric | Public baseline |
|---|---:|
| Hit Rate@10 | 0.125 |
| MRR | 0.068034 |
| MTTC | 9.81 |
| Efficiency | 0.119 |
| TechnicalScore | 0.10671 |

Source: [`baseline_results.json`](../docs/baseline_results.json).
A fresh evaluator run also gives the following scenario diagnosis:

| Scenario | Sessions | Hit Rate@10 | MRR | MTTC |
|---|---:|---:|---:|---:|
| Buying | 80 | 0.2375 | 0.126508 | 8.625 |
| Browsing | 80 | 0.025 | 0.004514 | 10.75 |
| Intent Override | 30 | 0.133333 | 0.104167 | 10.066667 |
| Boundary | 10 | 0.0 | 0.0 | 11.0 |

These values are reproducible public-development evidence, not private-set
performance. The near-zero Browsing and Boundary results point to dialogue and
state recovery as first-order gaps.

Its implementation is a stateless OR query over the current message. It indexes
`title`, `categories`, `features`, `details`, `store`, and `description`, but it:

- discards the aggregate profile;
- forgets previous messages and disclosed constraints;
- cannot represent negation, no-preference, or replacement;
- never asks a clarification question;
- has no structured price, rating, or field-specific reranking stage;
- has no complementary candidate route.

Low Hit Rate indicates candidate or intent-resolution failure. MRR being much
lower than Hit Rate also leaves room to improve ordering among successful
sessions. Diagnose these separately; a reranker cannot recover a target absent
from its candidate pool.

Reproduce the baseline without overwriting checked-in evidence:

```bash
python -m unittest discover -v
python -m evaluator.local_evaluator --output results_baseline_reproduced.json
```

The evaluator output includes scenario metrics even though the checked-in
baseline summary does not. Verify the catalog download against
[`SHA256SUMS`](../SHA256SUMS) before comparing scores.

## 5. Safe aggregate data findings

A read-only aggregate audit of the current 50,000-row catalog found:

- all `parent_asin` values are unique;
- all rows have the ten documented top-level fields;
- categories are present on every row, averaging 4.77 entries;
- features average 5.02 entries but are empty for 5,219 products;
- descriptions are empty for 23,887 products;
- details average 4.39 keys and use 287 distinct keys;
- store is missing for 314 products;
- price is missing for 39,473 products and has mixed numeric/string types;
- rating counts are strongly right-skewed (median 12, 90th percentile 260);
- average ratings are ceiling-heavy (median 4.2, 90th percentile 5.0).

A safe aggregate audit of the 200-row public set found 125 canonical aggregate
profiles, including repeated profiles, and the documented scenario counts of
80/80/30/10. These observations are development guidance, not private-set
claims. Recompute them after any data refresh and never print target IDs,
sample IDs, raw profiles, or target products in research reports.

Consequences:

- index fields separately and preserve both category paths and category tokens;
- recursively flatten detail key/value pairs with namespaced keys;
- represent missingness explicitly instead of treating missing price as zero;
- parse price strings defensively and apply numeric filters only when parsed;
- use `log1p(rating_number)` or a capped transform, not raw counts;
- shrink or confidence-weight average ratings rather than trusting 5.0 ratings
  with one review;
- use profile-grouped development splits to prevent identical profile records
  crossing tuning and holdout sets;
- do not assume constant or low-cardinality public profile fields behave the
  same way on the private set.

## 6. Recommended retrieval architecture

### 6.1 Catalog preparation

Build once per `Agent` instance:

- immutable set of valid `parent_asin` values;
- normalized raw text per field;
- field-specific sparse indexes;
- structured category, brand/store, material, color, size, price, and feature
  representations where catalog evidence supports extraction;
- catalog vocabularies and aliases used by the parser;
- quality features such as confidence-adjusted rating and review-count log;
- deterministic fallback ranking within coarse categories.

Normalize Unicode, case, whitespace, punctuation, common units, colors, and
materials, but retain original values and identifiers. Do not stem or collapse
product variants blindly: exact IDs remain distinct.

### 6.2 Session-state compiler

Keep bounded state per `session_id`:

```text
profile
message_history
active_positive_constraints
active_negative_constraints
soft_preferences
no_preference_attributes
superseded_constraints
asked_attributes
prior_recommendations
```

Interpret new evidence as typed operations:

- `add(attribute, value, strength)`;
- `negate(attribute, value)`;
- `replace(attribute, old_value, new_value)`;
- `no_preference(attribute)`.

Keep the current raw message alongside the parsed state. Use confidence-aware
extraction: an uncertain parser should preserve lexical evidence rather than
silently impose a destructive hard filter. Runtime state must remain isolated
by session and must never update a global profile or learned artifact.

### 6.3 Candidate generation

Measure routes independently before combining them:

1. current-turn fielded BM25;
2. resolved-state fielded BM25;
3. structured category/attribute route;
4. conservative fuzzy or character n-gram route;
5. optional frozen dense route.

Field weights should start with a small number of coarse presets: title and
category high, features/details medium, long description lower. If exact BM25F
is not implemented, describe a weighted sum of field scores accurately rather
than calling it BM25F.

Typo handling should be additive. Preserve the original query, avoid fuzzy
matching IDs/numbers/units, cap expansions, and give the fuzzy route lower
weight. A typo correction must not erase a valid brand or model token.

Dense retrieval is optional. With only 50,000 products, exact matrix similarity
against a precomputed local embedding matrix may be simpler and more
reproducible than a vector database. Benchmark cold load, warm latency, memory,
asset size, licensing, and offline availability before adoption.

### 6.4 Fusion and reranking

Use rank-based fusion when route score scales are incomparable. Reciprocal Rank
Fusion (RRF) is a strong low-parameter starting point:

```text
RRF(item) = sum_route weight_route / (k + rank_route(item))
```

Start with equal weights and a fixed `k`; tune only a few preregistered presets.
Then rerank a bounded union using:

1. hard-constraint eligibility and violation penalties;
2. current-message and active-state relevance;
3. exact phrase, title, category, and structured-field coverage;
4. soft preference and weak profile affinity;
5. confidence-adjusted product quality;
6. stable `parent_asin` tie-breaking.

Hard filters can catastrophically remove the target when parsing or metadata is
uncertain. Record target loss caused by each filter during offline diagnosis.
Use a relaxed parallel route or soft penalty for uncertain constraints.

### 6.5 Diversity

Diversity receives no direct score. Treat it as a Browsing recall hypothesis,
not a default objective. Preserve the strongest relevance-ranked positions and
only diversify near-tied lower positions across meaningful catalog aspects.
Never collapse distinct variants unless the official contract declares them
equivalent. Promote diversification only when exact Hit Rate/MRR improve.

## 7. Dialogue and clarification policy

Always provide the best current recommendations. A question is an additional
control action, not a substitute for retrieval.

A practical question policy:

1. Identify active constraints and attributes already asked or declined.
2. Estimate candidate uncertainty from route disagreement, top-score margins,
   candidate aspect entropy, and hard-constraint coverage.
3. For each allowed unasked attribute, estimate whether plausible answers would
   materially change top-10 membership or ordering.
4. Ask the highest-value, catalog-grounded attribute only if the expected gain
   exceeds a fixed threshold; otherwise set `ask_attribute=None`.
5. Prefer a typed attribute; use `other` only when evidence is unclassifiable or
   broad discovery is justified.

Scenario priors are useful policy hypotheses, not hidden runtime labels:

- **Buying:** enforce the disclosed hard constraint, rank immediately, and ask
  only for another discriminating attribute.
- **Browsing:** hedge with broad candidate recall and a high-value clarification.
- **Intent Override:** replace invalidated state immediately and avoid stale
  recommendations.
- **Boundary:** record unavailable preferences and continue without repetition.

Evaluate question policies end-to-end in the official public simulator. Static
logged conversations generally cannot tell what the customer would have said
to a different question; do not claim unbiased counterfactual gains from them.

## 8. Safe personalization

The supplied profile is an aggregate prior, not a hard statement of current
intent. Current explicit messages and constraints must dominate it.

Use preference tags and summary terms as weak boosts or tie-breakers. Treat
rating style and average prior rating cautiously. Never reconstruct identities,
reviews, purchases, or timestamps. Never persist one session's inferred
preferences into another.

Required ablation:

1. message/catalog only;
2. profile only as a diagnostic, not a proposed runtime system;
3. message/catalog plus profile;
4. shuffled or neutralized profile.

A profile feature earns inclusion only if it improves paired held-out results
without harming override behavior or hard-constraint satisfaction.

## 9. Experiment design for 200 public labels

The public set is small enough that model-selection noise is a major risk. One
Boundary session changes that slice's Hit Rate by 10 percentage points.
Repeatedly tuning against all 200 labels will create a convincing but brittle
public score.

### Fixed protocol

1. Freeze a deterministic, versioned split grouped by canonical profile and
   stratified as far as possible by scenario and difficulty.
2. Use tuning folds for parameter choices and preserve one untouched holdout.
3. Exclude `sample_id`, `ground_truth`, scenario labels, difficulty labels,
   intent cards, behavior, future turns, and evaluator internals from runtime
   features.
4. Change one hypothesis at a time and save results to a new file.
5. Compare variants per session, not only through aggregate means.
6. Report overall and scenario Hit Rate, MRR, MTTC, Efficiency, TechnicalScore,
   token use, cold initialization, warm-turn latency, and peak memory.
7. Use paired bootstrap intervals or a paired randomization test for important
   comparisons; report raw win/loss/tie counts too.
8. Promote only changes that improve the predeclared objective without a
   meaningful scenario or operational regression.
9. After promotion, freeze code/config/assets and avoid reusing holdout feedback
   for another tuning round.

### Retrieval diagnostics

For candidate pool sizes 10, 50, 100, and 500, record:

- target recall by retrieval route and by route union;
- target rank before and after reranking;
- target losses from parsing, filters, deduplication, and diversity;
- first hit turn and hit rank;
- candidate overlap and route contribution.

Use the following failure taxonomy:

1. target absent from all candidate routes;
2. target retrieved then filtered out;
3. target in pool but reranked below 10;
4. stale, negated, or overridden state error;
5. clarification selected the wrong or repeated attribute;
6. contract/output validation failure;
7. latency, model, dependency, or network failure.

Fix the dominant measured class rather than adding an unrelated component.

## 10. Prioritized experiment backlog

| Priority | Hypothesis | Minimum evidence |
|---:|---|---|
| 1 | Contract validation and deterministic fallback prevent avoidable misses | focused tests; clean-process identical outputs |
| 2 | Accumulated typed state improves multi-turn recall | candidate recall and official metrics, especially Override/Boundary |
| 3 | Field-aware current/resolved sparse routes beat one OR query | route recall, union recall, MRR, latency |
| 4 | Explicit hard/soft constraint semantics improve Buying precision | filter-loss audit and Buying metrics |
| 5 | Typed clarification reveals useful evidence earlier | MTTC and score versus no-question policy |
| 6 | Conservative fuzzy route recovers lexical misses | tagged typo cases plus held-out score |
| 7 | RRF improves hybrid union ordering | candidate recall unchanged; MRR/score improve |
| 8 | Weak profile boosts improve tie-breaking | profile/shuffle ablation |
| 9 | Frozen dense retrieval recovers semantic misses | unique route contribution exceeds memory/latency cost |
| 10 | Lower-rank diversity improves Browsing recall | exact score gain without MRR regression |
| 11 | LLM parsing/reranking fixes a measured residual class | gain survives offline fallback and cost disclosure |
| 12 | Prompt/evolution tooling improves a stable component | untouched-holdout gain after simpler methods plateau |

## 11. Reliability, safety, and submission readiness

- Load the catalog and indexes once per `Agent`, not once per turn.
- Validate every response against the contract and catalog ID set.
- Keep recommendations unique and deterministically ordered.
- Bound histories, candidate pools, retries, and model context.
- Treat catalog text as untrusted data when sent to a model: delimit it, never
  execute it, and schema-validate model output.
- Never send ground truth, public labels, evaluator state, future turns, raw
  labeled records, or secrets to an external service.
- Read credentials from environment variables and document provider, retention
  assumptions, approximate cost, tokens, and network dependency.
- Ship a deterministic offline fallback because official scoring may have no
  network access.
- Pin dependencies and model/assets; record licenses, checksums, generation
  commands, Python version, and hardware used for benchmarks.
- Test from a clean process and require identical serialized top-10 outputs.
- Keep runtime state session-local and discard it when lifecycle support exists.
- Never modify the catalog, evaluator, labels, scoring config, or baseline
  evidence to improve a reported score.

## 12. Demonstration and report plan

A strong final demonstration should show one concise session where the system:

1. returns valid recommendations immediately;
2. asks a specific, useful attribute;
3. incorporates the reply into visible structured state;
4. handles a correction or no-preference response without contradiction;
5. explains recommendations using catalog evidence;
6. succeeds with a high-ranked exact ID;
7. reports latency, token use, and offline fallback behavior.

The final report should include architecture, a retrieval-flow diagram,
ablation table, overall and scenario metrics, candidate-recall diagnosis,
cold/warm latency and memory, model/cost disclosure, deterministic fallback,
limitations, and exact reproduction commands. Clearly label public development
performance; never imply it is private-set performance.

## 13. Research sources and what they support

External sources justify mechanisms, not competition gains. Verify current
licenses and dependency costs before implementation.

| Source | Supported idea | Important limitation here |
|---|---|---|
| [Robertson & Zaragoza, BM25 and Beyond (2009)](https://doi.org/10.1561/1500000019) | BM25 term-frequency saturation, length normalization, and fielded extensions | Does not prescribe product-field weights |
| [Robertson, Zaragoza & Taylor, BM25F (CIKM 2004)](https://doi.org/10.1145/1031171.1031181) | Combining multiple weighted fields | Requires local ablation of weights |
| [Cormack, Clarke & Büttcher, RRF (SIGIR 2009)](https://doi.org/10.1145/1571941.1572114) | Rank-based fusion across incompatible score scales | Does not guarantee gains for this catalog |
| [Reimers & Gurevych, Sentence-BERT (EMNLP 2019)](https://arxiv.org/abs/1908.10084) | Independently encoded vectors for semantic similarity | STS results are not product-retrieval evidence |
| [Dalton, Xiong & Callan, TREC CAsT 2019](https://arxiv.org/abs/2003.13624) | Conversational query resolution as a retrieval problem | Open-domain passage retrieval, not shopping |
| [Aliannejadi et al., Qulac (SIGIR 2019)](https://arxiv.org/abs/1907.06554) | Clarification selection and use of prior QA context | Open-domain questions; thresholds do not transfer directly |
| [Carbonell & Goldstein, MMR (SIGIR 1998)](https://doi.org/10.1145/290941.291025) | Relevance/redundancy trade-off in reranking | Diversity is unscored and may hurt exact-ID MRR |
| [Cawley & Talbot, model-selection overfitting (JMLR 2010)](https://www.jmlr.org/papers/v11/cawley10a.html) | Finite-sample model selection can overfit its evaluation criterion | Requires disciplined splits; it offers no retrieval method |
| [Smucker, Allan & Carterette, IR significance tests (CIKM 2007)](https://doi.org/10.1145/1321440.1321528) | Paired topic-level comparison and randomization/bootstrap tests | Statistical significance does not replace practical effect size |
| [Li et al., unbiased offline policy evaluation (WSDM 2011)](https://doi.org/10.1145/1935826.1935878) | Counterfactual policy evaluation needs suitable randomized logs | Ordinary deterministic dialogue logs are insufficient |

Self-evolving prompt/code systems are not a primary research direction for this
submission. They add model-selection degrees of freedom, execution risk, API
cost, and public-set overfitting pressure before the basic retrieval problem is
solved. If used later, restrict them to offline, typed configuration proposals;
run the same tests and held-out gates as human-authored variants; never allow
runtime self-modification or execution of untrusted generated code.

## 14. Adoption rule

Start with contract correctness, explicit session state, field-aware sparse
retrieval, structured constraints, and a measured clarification policy. Add one
new mechanism only when a named failure class calls for it. Keep it only when a
reproducible ablation improves the official objective and remains safe,
offline-capable, deterministic, and explainable.
