# OSS universality audit (living doc)

Goals: module toggles, locale (en/ru), no personal data in git, config-driven text/paths, simple `/setup` onboarding.

## Fixed in recent commits

| Area | Status |
|------|--------|
| Cyrillic in `.py` | Moved to YAML (`onboarding_interview`, `vault_paths_locale`, `goals` regex) |
| Task search by `created_date` | `search_tasks(created_from/to, sort_by=created_asc)` |
| Task movement history | `get_task_timeline` + full log scan |
| Vault dashboard scaffold | `scaffold_vault_dashboards.py` + `vault_dashboards.{en,ru}.yaml.example` |
| `kanban_schema` locale | `kanban_schema.{en,ru}.yaml.example` + materialize on setup |
| `main_dashboard_md` in vault_paths | EN/RU filenames |

## Remaining gaps (priority)

### P0 — blocks fresh EN onboarding

1. **Author vault dashboards** (`🎯 Главный_Дашборд.md` in personal vault) are not auto-migrated — new users get scaffolded file; authors keep legacy files until `--force` or manual merge.
2. **`dashboard_templates.en.yaml.example`** is partial vs RU — expand section parity before calling finance OSS-complete.
3. **`config/vault_paths.yaml` on author machine** — may lack `main_dashboard_md` until merge from `.ru.yaml.example`.

### P1 — architecture / hardcode

4. **LLM call params** (`temperature`, `timeout`, `tool_choice`) — should live in `config/agent/platform.yaml` / model roles (user policy).
5. **Menu dispatch** (`if agent_app.has_domain…`, `BTN_BULK_ON`) — move to capability-driven registry like agent tools.
6. **`kanban_schema.yaml.example`** still RU-centric alias — prefer `kanban_schema.ru.yaml.example` only; deprecate generic `.example` duplicate.

### P2 — repo hygiene

7. **Maintainer / one-off scripts** in tree — audit `scripts/`, `planning_bot/tools/`, `knowledge_bot/tools/` for OSS vs author-only; extend `.gitignore` or move to `scripts/local/` (gitignored).
8. **`.txt` prompts** — prod `*.txt` gitignored ✓; ensure CI never copies personal prompts; `seed_planning_prompts` only from `.example.txt`.
9. **Regular processes** — verify `obsidian_sync.sh`, `run_finance_dashboard_daily.sh`, LaunchAgents documented in `DEPLOY_VPS.md` / `ONBOARDING.md`.

### P3 — i18n completeness

10. **Planning chart captions** — mostly in `domain_messages.{en,ru}` ✓; spot-check new chart scripts.
11. **Categories/priorities** — user-customizable via `kanban_schema.yaml`; onboarding interview should offer EN defaults for EN locale.
12. **Dataview dashboards** — tag prefixes from `kanban_schema.tag_prefixes`; quarter names in `vault_dashboards` strings.

## Verification checklist (CI / manual)

```bash
AGENT_LOCALE=en CAP_MODULE_FINANCE=1 ./scripts/setup.sh
./scripts/oa-python.sh scripts/apply_capabilities_profile.py --preset finance --write
./scripts/oa-python.sh scripts/init_vault_layout.py --vault "$VAULT_PATH"
./scripts/oa-python.sh -m pytest tests/test_no_cyrillic_in_py.py tests/test_vault_dashboard_scaffold.py -q
```

## Non-goals

- Migrating author's existing Obsidian notes automatically.
- Shipping personal `*.txt` prompts or vault content in git.
