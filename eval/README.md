# Eval

- **Agent harness (offline goldens):** [`eval/harness/`](harness/) — routing, category
  match, conversation contract. Run: `PYTHONPATH=. python -m eval.harness`
- **Retrieval:** gold `eval/gold/v0.yaml`; production dense vs catalog below.

# Retrieval eval

```bash
PYTHONPATH=. python eval/run_baselines.py \
  --gold eval/gold/v0.yaml --retrievers dense,catalog
```

Dense uses the same OpenRouter cache as prod (`knowledge_bot/data/dense_index.npz`).
Catalog is the LLM one-shot list (slow). Writes `eval/runs/<utc>/baselines.json`.

Known-item synthetic: `eval/retrieval_eval.py` runs live `run_brain_query`.
`--retrieve-only` skips the answer LLM.
