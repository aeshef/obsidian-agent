# Agent harness (golden baseline)

Offline checks for routing, tool contracts, and answer shape — no live LLM required
for the default suite.

## Run

```bash
cd Agent
PYTHONPATH=. finance_bot/.venv/bin/python -m eval.harness.run
# or:
PYTHONPATH=. finance_bot/.venv/bin/python eval/harness/run.py --cases eval/harness/cases
```

Exit code is non-zero when any case fails.

## Case format

YAML/JSON files under `eval/harness/cases/`:

```yaml
id: food-category-parent
kind: category_match
input:
  parent: Еда
  leaf: Еда/Вне дома
expect:
  matches: true
```

Supported `kind` values:

| kind | What it checks |
|------|----------------|
| `category_match` | hierarchical finance category matching |
| `cheap_router` | heuristic domain pick (or abstain) |
| `cross_domain` | finance×planning escalation patterns |
| `period_compare_format` | compare helper formatting |
| `conversation_contract` | host_query prompt contains contract markers |

Add new goldens here before wiring LLM-backed evals.
