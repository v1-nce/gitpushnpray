# Public-set train / validation / test split

`data/public_set.jsonl` (200 labeled sessions) is the only development data, so
reporting metrics on the whole file after tuning on it is "training on the test
set". These three files are the reproducible split that fixes that:

| file | sessions | buying | browsing | intent_override | boundary |
|---|---:|---:|---:|---:|---:|
| `train.jsonl` | 120 | 48 | 48 | 18 | 6 |
| `val.jsonl` | 40 | 16 | 16 | 6 | 2 |
| `test.jsonl` | 40 | 16 | 16 | 6 | 2 |

## Regenerate

```bash
python -m scripts.make_splits
```

This sorts by `sample_id`, stratifies by `scenario_type` (preserving the official
40/40/15/5 mix), and allocates 60/20/20 with largest-remainder rounding and a
seeded shuffle. Seed `20260830`. The output is byte-identical across clean
checkouts.

## Protocol

- **train** — do all architecture and tuning work here.
- **val** — choose between candidate variants here.
- **test** — run exactly once, at the end, and report that number. Never iterate
  on it.

## Known trade-off

Scenario stratification keeps the benchmark representative but allows a small
amount of cross-split profile reuse: 6 `train<->test`, 5 `val<->test`, and 10
`train<->val` sessions share an identical `user_profile`. With 200 sessions but
only 125 distinct profiles, representative scenario balance and zero profile
leakage cannot both be satisfied. If the profile feature is what is being tuned,
regenerate with `--group-by-profile`, which guarantees no profile crosses splits
at the cost of less exact scenario proportions.

## Honesty about the test split

The architecture was tuned against all 200 sessions before this split existed,
so the `test` split is a fresh measurement but not a pristine holdout — those 40
sessions already informed earlier design decisions. Treat the test number as a
lower-confidence generalization bound; the 800 private sessions remain the real
holdout.
