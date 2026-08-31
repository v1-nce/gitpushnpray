# TechJam Conversational E-Commerce Search Challenge

Build an AI shopping agent that asks useful follow-up questions and recommends the customer's hidden target product within at most 10 turns.

## What You Receive

- A frozen catalog of 50,000 products from the `Clothing_Shoes_and_Jewelry` category of Amazon Reviews 2023.
- 200 labeled public sessions for local development.
- A weak BM25 starter agent and deterministic local evaluator.
- The Agent API contract and scoring rules.

The organizer keeps 800 additional sessions private for final evaluation.

## Task

For each session, your agent receives an anonymized preference profile and a short customer message. Raw user IDs, review text, timestamps, and purchase history are never disclosed. On every turn the agent may:

- ask a natural clarification question in `message` and identify one requested field in `ask_attribute`;
- return a ranked list of up to 10 catalog `parent_asin` values;
- do both in the same response.

The session ends when the target product appears in the scored Top 10 or after turn 10. Sessions cover Buying, Browsing, Intent Override, and Boundary behavior.

## Current Solution

The repository now contains a deterministic, offline shopping agent rather than
the original stateless baseline. It builds in-memory SQLite FTS5, exact-evidence,
and category indexes once at startup. During a session it accumulates category
and constraint evidence, combines current-turn and resolved-state sparse routes,
reranks category-scoped evidence matches, and asks follow-up questions while
distinguishing preference reprioritization from explicit retraction.

No LLM, external API, credential, network connection, or third-party Python
package is required. See `documentations/ARCHITECTURE.md` for implemented versus
planned components.

## Download the Catalog

Download `catalog.jsonl.gz` from the GitHub Release attached to this repository, then run:

```bash
gzip -dk catalog.jsonl.gz
mv catalog.jsonl data/catalog.jsonl
```

Verify the downloaded file using the published `SHA256SUMS` file.

## Run and Test the Agent

Python 3.10 or later is recommended. The agent uses only the Python standard library.

```bash
python3 -m evaluator.local_evaluator
```

The command evaluates all 200 public sessions and writes per-session results and
aggregate metrics to the ignored local file `results.json`. Do not edit the
evaluator or public labels when reporting a local score.

Run the test suite:

```bash
python3 -m unittest discover -s tests -v
```

Run the deterministic catalog-disjoint paraphrase benchmark:

```bash
python3 -m scripts.shadow_evaluator \
  --sample-count 200 \
  --seed 20260830 \
  --output results_shadow.json
```

The shadow benchmark excludes all public target products, varies customer phrasing,
and publishes aggregate metrics without target IDs. It is a synthetic robustness
check, not an estimate of the organizer's private-set score.

Replay public evaluator conversations with product titles and target ranks:

```bash
python3 -X utf8 -m scripts.diagnose_sessions \
  public_0001 public_0006 public_0002 public_0035 --top-n 10
```

Role-play a shopper looking for a real random catalog product:

```bash
python3 -X utf8 -m scripts.chat_agent --random --seed 42
```

For a stronger manual stress test, describe the displayed product naturally
instead of copying its title or feature text.

## Public Development Results

| Agent | Hit Rate@10 | MRR | MTTC | Efficiency | TechnicalScore |
|---|---:|---:|---:|---:|---:|
| Released weak BM25 baseline | 0.125 | 0.068034 | 9.81 | 0.119 | 0.106710 |
| Current deterministic agent | **1.000** | **0.899409** | **2.070** | **0.893** | **0.948423** |

The current result was reproduced byte-for-byte in two clean evaluator processes.
Twenty-five focused unit tests pass. A clean public run took approximately 41 seconds on
the development machine, including index construction and all 200 sessions; runtime is
hardware-dependent.

These are public-development results, not private-set results. All 200 public
sessions were inspected during development, so they are no longer an unbiased
holdout. The simulator also returns catalog-grounded constraints close to
verbatim, which favors the exact-evidence route. Natural paraphrases and changed
dialogue templates remain important generalization risks. See
`results/EXPERIMENTS.md` for the experiment history and limitations.

## Generalization Results

Because the public set is saturated and was fully inspected during development, two
catalog-disjoint benchmarks estimate transfer to unseen products. They differ in one
variable so the causes can be told apart.

| Benchmark | Targets | Wording | Hit Rate@10 | MRR | MTTC | TechnicalScore |
|---|---|---|---:|---:|---:|---:|
| Official public set | seen | official | 1.000 | 0.899409 | 2.070 | 0.948423 |
| Unseen targets, seed `20260830` | unseen | official | 0.995 | 0.899560 | 2.125 | **0.944868** |
| Paraphrase V1, seed `20260830` | unseen | rewritten | 0.980 | 0.855415 | 2.525 | 0.916125 |

Both benchmarks draw one unseen product per public target from the same review-count
band. This matters more than it sounds: official targets are real purchase records with
a median of 7078 reviews, against 12 for the catalog as a whole, so sampling the catalog
uniformly builds a long-tail test set the organizer would never present. Earlier
revisions of this table used uniform sampling and understated both scores by 0.06 to
0.10. Pass `--uniform-targets` to reproduce that pool.

Unseen target products cost 0.004; unfamiliar wording costs a further 0.029.

The unseen-target score varies with the draw of products. Seed `20260830` above was
used for every development decision, so two seeds never used for any choice were run
as a sealed check: `31337` scores 0.918981 and `987654` scores 0.942379. Report the
expected private score as **0.92 to 0.945**, centred near **0.935**, rather than as a
single figure. The specification reserves the right to add natural-language
paraphrasing, in which case the lower paraphrase figure is the better guide. See
[`008_unseen_popularity_matched.json`](results/008_unseen_popularity_matched.json) and
[`009_shadow_popularity_matched.json`](results/009_shadow_popularity_matched.json).

Run them with:

```bash
python3 -m scripts.unseen_target_evaluator --sample-count 200 --seed 20260830
python3 -m scripts.shadow_evaluator --sample-count 200 --seed 20260830
```

## Agent Interface

```python
class Agent:
    def reset(self, session_id: str, user_profile: dict) -> None:
        ...

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        return {
            "message": "Do you have a material preference?",
            "ask_attribute": "material",
            "recommendations": [
                {"parent_asin": "B000..."},
                {"parent_asin": "B001..."}
            ],
            "usage": {"prompt_tokens": 120, "completion_tokens": 30}
        }
```

`ask_attribute` is one of `category`, `material`, `color`, `size`, `style`, `brand`, `budget`, `feature`, `use_case`, `other`, or `null`. See `docs/agent_api_contract.json`.

## Technical Metrics

- **Hit Rate@10:** fraction of sessions that find the target within 10 turns.
- **MRR:** mean reciprocal rank of the target; a miss contributes zero.
- **MTTC:** mean first-hit turn; a miss is assigned turn 11.
- **Reported token usage:** prompt and completion tokens returned by the team's model client.

```text
TechnicalScore = 0.50 × HitRate@10 + 0.30 × MRR + 0.20 × Efficiency
Efficiency = clip((11 - MTTC) / 10, 0, 1)
```

Only exact `parent_asin` equality produces a hit. Core metrics are also reported by scenario.

## Model Choice and Cost

The current implementation uses deterministic Python and SQLite FTS5. It reports
zero model tokens and has no API cost or network dependency. Dense retrieval and
LLM reranking are intentionally deferred until an offline experiment demonstrates
a reproducible gain that justifies their latency, memory, and cost.

Measured runtime cost from [`results/013_runtime_cold_index_cache.json`](results/013_runtime_cold_index_cache.json)
and [`results/014_runtime_warm_index_cache.json`](results/014_runtime_warm_index_cache.json)
on the development machine (Python 3.13.5): a 11.7 s one-time cold build, then a
0.34 s warm start from the derived `data/catalog.jsonl.index.db` snapshot, ~289-302 MB
agent resident memory, and 19-30 ms p50 / 57-85 ms p95 per-response latency. The cache
regenerates automatically when the catalog file changes. Reproduce with:

```bash
python3 -X utf8 -m scripts.benchmark_runtime --output results/NNN_slug.json
```

## Files

```text
data/public_set.jsonl             200 labeled development sessions
docs/competition_specification.md participant rules and evaluation protocol
docs/agent_api_contract.json      machine-readable Agent contract
docs/evaluation_config.json       scoring configuration
docs/baseline_results.json        reproducible weak-starter reference score
starter/agent.py                  current deterministic hybrid agent
evaluator/local_evaluator.py      public-set simulator and scorer
scripts/diagnose_sessions.py      public conversation replay and failure inspection
scripts/chat_agent.py             manual role-play against a known catalog target
scripts/shadow_evaluator.py       catalog-disjoint paraphrase robustness benchmark
scripts/unseen_target_evaluator.py official-wording unseen-target private-set proxy
scripts/benchmark_runtime.py      cold-start, memory, and per-response latency benchmark
tests/test_agent.py               state, evidence, and clarification tests
results/EXPERIMENTS.md           public experiment history and limitations
```

## Judging and Submission Policy

- Participant submission requirements: [`docs/submission_rules.md`](docs/submission_rules.md)
- Submission report: [`docs/SUBMISSION_REPORT.md`](docs/SUBMISSION_REPORT.md)
- Participant release checklist: [`docs/RELEASE_CHECKLIST.md`](docs/RELEASE_CHECKLIST.md)

## Data Source

The catalog and sessions are derived from Amazon Reviews 2023 by McAuley Lab, UCSD. See `DATA_ATTRIBUTION.md` before using or redistributing the data.
Sessions are sampled deterministically from the official Clothing 5-core leave-last-out split and joined to the frozen catalog.
