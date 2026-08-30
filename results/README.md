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

## How to record a new experiment

1. Make the code change on a branch.
2. Run the relevant evaluator and write the artifact:
   ```bash
   python -X utf8 -m evaluator.local_evaluator --output results/NNN_slug.json
   # or
   python -X utf8 -m scripts.shadow_evaluator --output results/NNN_slug.json
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
- Never overwrite `docs/baseline_results.json`, `docs/evaluation_config.json`,
  the evaluator, or public labels to change a reported score.
- Raw JSON is the source of truth; the markdown tables are an index, so update
  both when adding a run.
