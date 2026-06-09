# OSS universality audit (living doc)

Last review: 2026-06-09. Goals: module toggles, locale (en/ru default), no personal data in git, config-driven text/paths/numbers, simple `/setup` + onboarding skill.

## Philosophy checklist

| Principle | Status |
|-----------|--------|
| Unified bot (merged infra) | `unified_bot` + shared host |
| Modular domains/connectors/features | `capabilities.yaml` + env `CAP_*` |
| Agent NL loop for free text | `shared/agent` — menus are optional shortcuts |
| No Cyrillic in `.py` | CI `test_no_cyrillic_in_py.py` |
| Text/numbers in YAML | `messages`, `domain_messages`, `platform.yaml`, bot configs |
| Prompts `.example.txt` in git | prod `.txt` gitignored |
| Default locale EN | `AGENT_LOCALE=en`, `materialize_locale.py` |
| No personal data in commits | vault paths via examples; author vault gitignored |

## Done (recent)

| Area | Notes |
|------|-------|
| Daily check-in | `planning_daily_checkin` feature; routines toggle + signals history |
| Config | `daily_checkin.yaml.example`, `platform.yaml` `planning_checkin` |
| Vault | `signals_subdir`, `signals_history_md` in `vault_paths.*.example` |
| Scheduler | 23:45 prompt; passive 21–23 disabled when check-in on |
| UI | `auto_checkin_close`, `show_routines_menu` wired in `menu_actions` |
| Tests | `tests/test_daily_checkin.py` |

## Remaining (priority)

### P1 — architecture / hardcode

1. **LLM default params in signatures** — move remaining `temperature`/`timeout` defaults in `shared/llm.py` callers to `config/agent/models.yaml` only (no numeric literals in `.py` signatures).
2. **Menu routing** — legacy `domain_dispatch.py` string compares (`BTN_BULK_ON`, domain `if` chains); migrate to `ui_capabilities` reply specs.
3. **`resolve_shell_msg.py` JSON** — deploy log noise when kwargs passed from shell.
4. **Author vault_paths** — merge new `signals_*` keys into local `config/vault_paths.yaml` (run `./scripts/setup.sh` or materialize).

### P2 — repo hygiene

5. **Maintainer scripts** — audit `planning_bot/tools/`, `knowledge_bot/tools/`, one-off `scripts/`; move author-only to `scripts/local/` + gitignore.
6. **Regular processes** — document LaunchAgents + crontab (`cron_routines.sh` 01:00, obsidian_sync) in `DEPLOY_VPS.md`.
7. **Signals export** — optional `signals_week.json` for dashboard charts (phase 2).

### P3 — polish

8. Onboarding interview — EN default categories from `kanban_schema.en`.
9. Morning routine block in check-in (separate 10:00 job).
10. Agent tool `get_daily_signals` for NL queries.

## Verification

```bash
AGENT_LOCALE=en ./scripts/setup.sh
./scripts/oa-python.sh scripts/materialize_locale.py en
./scripts/oa-python.sh -m pytest \
  tests/test_no_cyrillic_in_py.py \
  tests/test_daily_checkin.py \
  tests/test_ui_bindings.py -q
```

## Non-goals

- Auto-migrate author Obsidian notes (`🎯 Главный_Дашборд.md`).
- Ship prod prompts or personal vault content in git.
