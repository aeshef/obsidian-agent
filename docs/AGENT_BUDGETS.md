# Agent context budgets — knob registry (owners + how to calibrate)

Numbers that change answer quality live in YAML, not call sites. Prefer
`scripts/calibrate_agent_budgets.py` over guessing.

## Owners

| Cluster | Config | Owner | Calibrate with |
|---------|--------|-------|----------------|
| Loop budgets | `platform.yaml` → `agent.max_*` | harness | `end_reason` in `agent_traces` |
| Tool/verify clip | `agent.tool_result_max_chars`, `models.yaml` → `verify.tools_excerpt_max_chars`, `agent_budgets.*` | harness | `tool_clip_ratio`, calibrate script |
| Activity dumps | `planning_action_log.*` (+ `activity_events_single_day_limit`) | planning | day dump sizes vs clip |
| Session / classify clips | `agent.session_max_turns`, `llm_classify.dialogue_hint_*` | harness | follow-up quality / basket |
| Working set | `memory.yaml` → `working_set.*` | memory | follow-up entity recall |
| Situation HUD | `memory.yaml` → `situation.*` | memory | morning “what’s today” |
| Series helpers | `series_tools.*` | harness | join/tally completeness |
| Health defaults | `planning_health.*` | planning | anomaly false positives |
| Knowledge retrieval | `knowledge_query.*` | knowledge | `eval/run_baselines.py` |
| Cascade / models | `models.yaml` → `cascade`, roles | harness | escalate reasons in traces |

## Spec rules (not vibes)

1. **Single calendar day** activity queries use `activity_events_single_day_limit` (default `0` = full day) when the tool `limit=-1` (auto).
2. **tool_result_max_chars** should be ≥ p95(full day dump chars) × `agent_budgets.headroom`, clamped to `[floor_chars, ceiling_chars]`.
3. Optional `config/agent/budget_stats.json` (gitignored) raises the effective floor after `--write`.

## Observability

`logs/agent_traces.jsonl` fields (no message bodies):

- `tool_clip_ratio`, `tool_raw_chars_sum`, `tool_llm_chars_sum`, `tool_clipped_count`
- `cascade_escalate_reasons`, `verify_ok`, `verify_rewrote`
- `session_messages`, `working_set_items`, `core_priors_lines`
- existing: `end_reason`, `context_chars_peak`, `est_cost_usd`

Weekly rollup (`trace_analytics`) also surfaces avg clip ratio, max_iters / tool_budget rates.

## Compact activity dumps

`get_activity_events(summary=auto|unique|full|raw)`:

- `auto` → `unique` on a single calendar day, else `full`
- `unique` → unique completions + counts (no moved spam)

Facade: `shared.agent.budget_caps.AgentContextBudget`.

## Commands

```bash
PYTHONPATH=. ./scripts/oa-python.sh scripts/calibrate_agent_budgets.py --days 21
PYTHONPATH=. ./scripts/oa-python.sh scripts/calibrate_agent_budgets.py --write
PYTHONPATH=. ./scripts/oa-python.sh scripts/mine_session_basket.py
PYTHONPATH=. ./scripts/oa-python.sh scripts/score_agent_basket.py --only-labeled
PYTHONPATH=. ./scripts/oa-python.sh -m eval.harness.run
```

## Review basket

- Public patterns: `eval/gold/basket_draft.example.yaml`
- Personal labels: `eval/gold/local_basket.yaml` (gitignored; from mine script)
- Attach `expected_facts` / `forbidden_facts` and score with `score_agent_basket.py`
- Context-sensitive rows need frozen `expected_facts` or will drift with the vault.
