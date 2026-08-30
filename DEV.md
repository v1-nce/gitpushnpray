# Dev Loop

Repeat this cycle. Change **one** thing per pass.

1. **Edit** `starter/agent.py`.

2. **Sanity check** — fast, catches contract breaks:
   ```bash
   python -m unittest discover -s tests -v
   ```

3. **Score** all 200 public sessions (write to a scratch file, never `results.json`):
   ```bash
   python -m evaluator.local_evaluator --output results_candidate.json
   ```

4. **Compare** against the baseline in `docs/baseline_results.json` and your previous
   `results_candidate.json`. Look at overall **and** per-scenario Hit@10 / MRR / MTTC.
   A small overall gain can hide a Buying / Browsing / Intent Override / Boundary regression.

5. **Diagnose** any miss or regression — replay the conversation with product titles,
   target rank, resolved state, and evidence matches:
   ```bash
   python -X utf8 -m scripts.diagnose_sessions public_0001 public_0006 --top-n 10
   ```
   Classify the failure: retrieval recall / reranking rank / state parsing / dialogue policy.

6. **Decide** the next single change from that diagnosis. Go to 1.

## Rules

- Keep exploratory output in `results_candidate.json`. Only regenerate `results.json`
  with a plain `python -m evaluator.local_evaluator` when you deliberately update the
  checked-in default.
- Never edit `evaluator/`, `data/public_set.jsonl`, or `docs/baseline_results.json` to move a score.
- Public results are development numbers, not private-set estimates — all 200 sessions
  are seen during tuning. Record each pass in `documentations/EXPERIMENTS.md`.

## Manual smoke test

Role-play a shopper against a random known catalog target (describe the product in your
own words, don't copy its title):
```bash
python -X utf8 -m scripts.chat_agent --random --seed 42
```
