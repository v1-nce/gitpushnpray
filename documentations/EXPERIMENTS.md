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

| Version | Main change | Hit Rate@10 | MRR | MTTC | TechnicalScore |
|---|---|---:|---:|---:|---:|
| Released baseline | Stateless single-query BM25 | 0.125 | 0.068034 | 9.810 | 0.106710 |
| Stateful evidence V1 | Accumulated state, exact evidence, multi-route sparse retrieval | 0.950 | 0.663776 | 2.595 | 0.842233 |
| Parser and exploration | Correct no-preference parsing and unseen-candidate exploration | 0.955 | 0.657484 | 2.585 | 0.843045 |
| Category-scoped evidence | Prevent generic attributes from dominating across categories | 0.995 | 0.694296 | 2.205 | 0.881689 |
| Current | Repeat a productive typed clarification once | **1.000** | **0.699296** | **2.175** | **0.886289** |

Current scenario Hit Rate@10 is 1.0 for Buying, Browsing, Intent Override, and
Boundary. The complete output was byte-identical across two clean evaluator
processes (SHA-256 `7A3A43BF490FE4D985C11747A2B5F4BEC6058D84BCB429B46720A088574EC05D`).
One complete run took approximately 33.2 seconds including index construction
and all conversations. Seven focused unit tests pass.

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
- Indexes are rebuilt for each clean process; persistence, cold-start memory,
  and peak-memory benchmarks remain future work.

## Reproduction

```bash
python3 -m unittest discover -s tests -v
python3 -m evaluator.local_evaluator
python3 -X utf8 -m scripts.diagnose_sessions public_0001 --top-n 10
python3 -X utf8 -m scripts.chat_agent --random --seed 42
```

## Next experiments

1. Generate protocol-compatible sessions for catalog targets outside the 200
   public targets to test unseen-product transfer.
2. Add a paraphrase stress set and measure the drop from exact catalog wording.
3. Accumulate materials, colors, brands, sizes, budgets, negations, and
   corrections from arbitrary customer sentences rather than fixed templates.
4. Compare the fixed question policy with category-grounded candidate entropy
   or expected information gain.
5. Improve ordering among products that share all disclosed evidence, targeting
   MRR without sacrificing Hit Rate or MTTC.
6. Benchmark persistent indexes, cold/warm latency, and peak memory before
   adding embeddings or an LLM reranker.
