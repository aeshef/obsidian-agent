# Retrieval gold sets

Labeled queries for known-item retrieval eval (`eval/run_baselines.py`, `eval/retrieval_eval.py`).

## Public vs private

| File | Tracked? | Purpose |
|------|----------|---------|
| **`public_v0.yaml`** | Yes (OSS) | Synthetic, PII-free English queries for a generic vault. Use this in CI/docs and contributor runs. |
| `v0.yaml` | No (local) | Author’s human-labeled set (personal vault paths/queries). |
| `frozen_eval_v0.yaml` | No (local) | Frozen synthetic set from a private `results.json` run. |
| `teacher_v0.yaml` | No (local) | Large teacher/candidate pool before curation. |

Private YAML under this directory is gitignored (see root `.gitignore`: `eval/gold/*.yaml` with `!public_*.yaml`). Do not commit personal queries, names, employers, or city-identifying paths.

## How to run

From the repo root (with `VAULT_PATH` and LLM keys in `.env`):

```bash
# Blind baselines (dense / catalog) against the public gold
PYTHONPATH=. python eval/run_baselines.py \
  --gold eval/gold/public_v0.yaml --retrievers dense,catalog

# Live known-item synthetic (samples notes from your vault; writes local artifacts)
PYTHONPATH=. python eval/retrieval_eval.py --n 25 --seed 7 --retrieve-only
```

`run_baselines.py` writes under `eval/runs/` (gitignored). `retrieval_eval.py` defaults to `eval/results.json` (also gitignored).

Schema: each row needs `query` plus `relevant_paths` (empty only for `bucket: refuse`). Rows with `status: needs_label` or `draft` are skipped by `eval.retrieval.gold.load_gold`.

## Metrics (public)

Public Recall@1 / MRR for `public_v0.yaml` are **not published yet**.

Local maintainer runs may produce `eval/results.json` / `eval/runs/*/baselines.json`, but those artifacts are gitignored and often reflect a private vault — do not treat them as OSS baseline numbers.

When a public baseline is available, record it here, for example:

```text
# placeholder — fill after a public-vault run
# gold: public_v0.yaml
# Select Recall@1: —
# MRR: —
```
