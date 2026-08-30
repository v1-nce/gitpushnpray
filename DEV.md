# Dev Loop

Repeat this cycle. Change **one** thing per pass.

**Data discipline:** `data/public_set.jsonl` is carved into train/val/test by
`scripts/make_splits.py` (60/20/20, seed `20260830`; see `data/splits/README.md`).
Tune on train, select on validation, and run test exactly once as the final
benchmark. Never report the full-200 number as performance — that is training on
the test set.

1. **Edit** `starter/agent.py`.

2. **Sanity check** — fast, catches contract breaks:
   ```bash
   python -m unittest discover -s tests -v
   ```

3. **Tune** on the train split:
   ```bash
   python -X utf8 -m evaluator.local_evaluator --dataset data/splits/train.jsonl --output results_candidate_train.json
   ```

4. **Select** between variants on validation:
   ```bash
   python -X utf8 -m evaluator.local_evaluator --dataset data/splits/val.jsonl --output results_candidate_val.json
   ```

5. **Diagnose** a miss or regression on a *train* sample (never test):
   ```bash
   python -X utf8 -m scripts.diagnose_sessions public_0001 --dataset data/splits/train.jsonl --top-n 10
   ```
   Classify the failure: retrieval recall / reranking rank / state parsing / dialogue policy.

6. **Promote** the change only when train and validation both improve, then record
   it in `results/EXPERIMENTS.md` and `results/README.md` (new id, parent id).

7. **Benchmark** the final chosen variant once on test:
   ```bash
   python -X utf8 -m evaluator.local_evaluator --dataset data/splits/test.jsonl --output results/NNN_slug.json
   ```
   That test number is the reported benchmark. Do not iterate on it.

8. **Decide** the next single change from the diagnosis. Go to 1.

## Rules

- Keep exploratory output in `results_candidate_*.json`. Never overwrite a
  committed artifact in place; a new change gets a new id.
- Never edit `evaluator/`, `data/public_set.jsonl`, the committed split files, or
  `docs/baseline_results.json` to move a score.
- Regenerate splits only with the fixed seed: `python -m scripts.make_splits`.
- Public results are development numbers, not private-set estimates — the test
  split is the reported benchmark, and the 800 private sessions are the real
  holdout.

## Manual smoke test

Role-play a shopper against a random known catalog target (describe the product in
your own words, don't copy its title):
```bash
python -X utf8 -m scripts.chat_agent --random --seed 42
```
