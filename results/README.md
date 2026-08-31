# Experiment results

Raw, machine-readable evaluator outputs. Public artifacts are written by
`evaluator/local_evaluator.py`; shadow artifacts are written by
`scripts.shadow_evaluator`. Each artifact identifies its benchmark and is the
**authoritative record** of that run.

## Naming convention

```
results/NNN_slug.json
```

- `NNN` — zero-padded, strictly increasing experiment id. Never reused.
- `slug` — short, human-readable label (lower_snake_case).
- One experiment = one file = one evaluator or shadow-benchmark run.

The human-readable lineage, narrative, and side-by-side metrics live in
[`EXPERIMENTS.md`](EXPERIMENTS.md). That table is the index; these JSON files
are the data.

## Lineage (parent -> child)

| id | slug | parent | artifact | change |
|---|---|---|---|---|
| 000 | weak_bm25_starter | — | [`../docs/baseline_results.json`](../docs/baseline_results.json) | Stateless single-query BM25 starter |
| 001 | stateful_hybrid | 000 | [`001_stateful_hybrid.json`](001_stateful_hybrid.json) | Accumulated state, exact evidence, multi-route sparse retrieval |
| 002 | lexicographic_v1 | 001 | [`002_lexicographic_v1.json`](002_lexicographic_v1.json) | Constraint-lattice ranker, hard/soft demotion, evidence ladder, confidence gate |
| 003 | shadow_paraphrase_v1 | 002 | [`003_shadow_paraphrase_v1.json`](003_shadow_paraphrase_v1.json) | Catalog-disjoint dialogue benchmark plus parser wrapper normalization |
| 004 | runtime_v1 | 003 | [`004_runtime_v1.json`](004_runtime_v1.json) | Cold-start, memory, and per-response latency measurement; no agent change |
| 005 | unseen_official_v1 | 004 | [`005_unseen_official_v1.json`](005_unseen_official_v1.json) | Official dialogue policy on catalog-disjoint targets; isolates unseen products from paraphrasing. No agent change |
| 006 | embedded_phrase_v1 | 005 | [`006_embedded_phrase_v1.json`](006_embedded_phrase_v1.json) | Match the longest catalog phrase embedded in a payload, merged with the typed route (public run) |
| 007 | embedded_phrase_shadow | 006 | [`007_embedded_phrase_shadow.json`](007_embedded_phrase_shadow.json) | Same change measured on the paraphrase benchmark |
| 008 | unseen_popularity_matched | 007 | [`008_unseen_popularity_matched.json`](008_unseen_popularity_matched.json) | Unseen-target benchmark with targets popularity-matched to the public set. Supersedes 005. No agent change |
| 009 | shadow_popularity_matched | 008 | [`009_shadow_popularity_matched.json`](009_shadow_popularity_matched.json) | Paraphrase benchmark with the same sampling correction. Supersedes 003 and 007. No agent change |
| 010 | emit_fill_public | 009 | [`010_emit_fill_public.json`](010_emit_fill_public.json) | Fill Top-10 from the full ranking once no clarification question remains (public run) |
| 011 | emit_fill_unseen | 010 | [`011_emit_fill_unseen.json`](011_emit_fill_unseen.json) | Same change measured on the unseen-target official-wording benchmark |
| 012 | emit_fill_shadow | 011 | [`012_emit_fill_shadow.json`](012_emit_fill_shadow.json) | Same change measured on the paraphrase benchmark; Hit 0.945->0.980, shadow 0.916125 |
| 013 | runtime_cold_index_cache | 012 | [`013_runtime_cold_index_cache.json`](013_runtime_cold_index_cache.json) | Cold build plus steady-state latency with the persisted-index code path (first run) |
| 014 | runtime_warm_index_cache | 013 | [`014_runtime_warm_index_cache.json`](014_runtime_warm_index_cache.json) | Warm restore plus steady-state latency; construction 0.34 s vs 11.7 s cold |

## How to record a new experiment

1. Make the code change on a branch.
2. Run the relevant evaluator and write the artifact:
   ```bash
   python -X utf8 -m evaluator.local_evaluator --output results/NNN_slug.json
   # or
   python -X utf8 -m scripts.shadow_evaluator --output results/NNN_slug.json
   # or, for the private-set proxy at official wording
   python -X utf8 -m scripts.unseen_target_evaluator --output results/NNN_slug.json
   # or, for a runtime and memory measurement rather than a score
   python -X utf8 -m scripts.benchmark_runtime --output results/NNN_slug.json
   ```
3. Append exactly one pointer row to the lineage table in this README **and** to
   the table in [`EXPERIMENTS.md`](EXPERIMENTS.md) — id, slug, parent id,
   one-line change, and artifact link. No narrative prose; it is one more entry
   in a list.
4. Record the result honestly: public-set numbers are development evidence, not
   private-set performance. Note reverted or dead-end experiments too — lineage
   is a graph, not only the winning path.

## Rules

- Never edit a committed artifact in place; a new change gets a new id.
- Artifacts 003, 005 and 007 were produced with uniform target sampling and are
  superseded by 008 and 009. They are retained because they are the record of what
  was measured at the time, not because their numbers still stand.
- Never overwrite `docs/baseline_results.json`, `docs/evaluation_config.json`,
  the evaluator, or public labels to change a reported score.
- Raw JSON is the source of truth; the markdown tables are an index, so update
  both when adding a run.
