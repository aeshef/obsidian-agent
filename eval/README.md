# Eval

- **Agent harness (offline goldens):** [`eval/harness/`](harness/) — routing, category
  match, conversation contract, **budget clip / activity limit policy**.
  Run: `PYTHONPATH=. python -m eval.harness`
- **Budgets:** [`docs/AGENT_BUDGETS.md`](../docs/AGENT_BUDGETS.md) +
  `scripts/calibrate_agent_budgets.py` / `scripts/mine_session_basket.py`
- **Review basket:** [`eval/gold/basket_draft.example.yaml`](gold/basket_draft.example.yaml);
  personal labels in `eval/gold/local_basket.yaml` (gitignored)
- **Retrieval:** public gold [`eval/gold/public_v0.yaml`](gold/public_v0.yaml)
  (see [`eval/gold/README.md`](gold/README.md)); private labeled sets stay local/gitignored.

# Retrieval eval

```bash
PYTHONPATH=. python eval/run_baselines.py \
  --gold eval/gold/public_v0.yaml --retrievers dense,catalog
```

Dense uses the same OpenRouter cache as prod (`knowledge_bot/data/dense_index.npz`).
Catalog is the LLM one-shot list (slow). Writes `eval/runs/<utc>/baselines.json`.

Known-item synthetic: `eval/retrieval_eval.py` runs live `run_brain_query`.
`--retrieve-only` skips the answer LLM.
