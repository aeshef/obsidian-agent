# OSS universality audit (living doc)

Goals: module toggles, locale (en/ru), no personal data in git, config-driven text/paths, simple `/setup` onboarding.

## Done

| Area | Status |
|------|--------|
| Cyrillic in `.py` | YAML (`onboarding_interview`, `vault_paths_locale`, `goals` regex) |
| Task `created_date` + timeline | `search_tasks`, `get_task_timeline` |
| Vault dashboard scaffold | `vault_dashboards.{en,ru}.yaml.example` + `vault-templates/dashboards/` |
| `kanban_schema` locale | `{en,ru}.yaml.example` + `materialize_locale.py` |
| `dashboard_templates` locale | Full EN/RU `.yaml.example` + key-tree test |
| `main_dashboard_md` in vault_paths | EN/RU filenames |
| LLM temps/timeouts/tool_choice | `config/agent/models.yaml` + `shared/llm_defaults.py` |
| Deploy assets | `vault-templates/` rsync on deploy |
| Setup | `scaffold_vault_dashboards.py` when `VAULT_PATH` + `capabilities.yaml` exist |
| Menu actions | `config/ui_capabilities.yaml` → `menu_actions_config.py` (labels via messages) |

## Remaining (priority)

### P1

1. **Author vault** — legacy `🎯 Главный_Дашборд.md` not auto-migrated; use `scaffold_vault_dashboards.py --force` or merge manually.
2. **Menu routing** — domain text still routed via `domain_dispatch.py` + per-bot `menu_dispatch`; consolidate bulk/KB buttons into `ui_capabilities` reply specs fully.
3. **`kanban_schema.yaml.example`** — deprecated alias; remove after one release cycle.

### P2

4. **Author-only scripts** — audit `planning_bot/tools/`, `knowledge_bot/tools/`, one-off `scripts/`; gitignore or `scripts/local/`.
5. **`resolve_shell_msg.py` JSON** — deploy log noise (cosmetic).
6. **Regular processes** — document LaunchAgents in `DEPLOY_VPS.md` (partial).

### P3

7. Onboarding interview EN default categories from `categories_mvp.en` / `kanban_schema.en`.
8. Planning chart scripts — spot-check new `pdmsg` keys in both locales.

## Verification

```bash
AGENT_LOCALE=en ./scripts/setup.sh
./scripts/oa-python.sh scripts/apply_capabilities_profile.py --preset finance --write
./scripts/oa-python.sh scripts/init_vault_layout.py --vault "$VAULT_PATH"
./scripts/oa-python.sh -m pytest \
  tests/test_no_cyrillic_in_py.py \
  tests/test_vault_dashboard_scaffold.py \
  tests/test_dashboard_templates_locale.py -q
```

## Non-goals

- Auto-migrate author Obsidian notes.
- Ship prod `*.txt` prompts or personal vault content in git.
