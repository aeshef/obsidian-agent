# OSS universality audit (living doc)

Last review: 2026-06-10 (KB save + vault maintenance audit).  
North star: one repo, any locale, any module subset, no author identity in git, config-driven everything, setup via onboarding skill + env.

## Philosophy scorecard

| Principle | Status | Evidence / gap |
|-----------|--------|----------------|
| **Unified host** | ✅ | `unified_bot` + `shared/telegram/host` |
| **Modular bots** | ✅ | `capabilities.yaml` + `CAP_*` + feature gates (`planning_daily_checkin`, …) |
| **Agent NL loop** | ⚠️ | Free text → agent; menus still parallel path via `menu_dispatch` / legacy `domain_dispatch` |
| **No Cyrillic in `.py`** | ✅ | `tests/test_no_cyrillic_in_py.py` |
| **Text in YAML** | ⚠️ | `messages.*`, `domain_messages.*`, bot YAML; check-in had `**markdown**` without `parse_mode` → fixed in examples |
| **Numbers in YAML** | ⚠️ | `platform.yaml`, `models.yaml`; literals remain in some LLM call sites (see P1) |
| **Paths in YAML** | ✅ | `vault_paths.{en,ru}.yaml.example`; deploy no longer overwrites author `vault_paths.yaml` |
| **Prompts in files** | ✅ | `*.example.txt` in git; prod `*.txt` gitignored |
| **Default locale EN** | ✅ | `AGENT_LOCALE=en`; author personalizes via `materialize_locale.py` + local YAML |
| **No personal data in git** | ✅ | vault, prod prompts, `vault_paths.yaml`, `badge.yaml` gitignored |
| **Simple setup** | ✅ | `scripts/setup.sh`, `.cursor/skills/obsidian-agent-onboarding/SKILL.md` |

## Verified: daily check-in E2E (2026-06-09 prod)

| Artifact | Path (author vault, RU) | Status |
|----------|---------------------------|--------|
| Signals history | `400_Рутины/📊 Сигналы/📊 История_Сигналов.md` | ✅ YAML block + summary |
| Sample entry | `mood:5, energy:3, stress:2, focus:карьера, day_quality:4` | ✅ |
| Routines today | `400_Рутины/📅 Рутины/📅 Сегодня.md` | ✅ toggles applied (e.g. Зал → `[x]`) |
| Scheduler | `send_daily_checkin_prompt` 23:45 MSK | ✅ in APScheduler log |

## Done (2026-06-10 session)

| Area | Change |
|------|--------|
| KB save (no bulk) | `templates_path` → vault `800_*/Templates/Clones` (was `knowledge_bot/templates/`) |
| KB LLM payloads | `enums_for_llm_payload()` — frozenset → sorted list (fixes `json.dumps` in route/field_fill/tags) |
| Maintenance audit ✗ | `VisionRateLimitError` re-export from `extract`; dry-run dup lines via `dup_delete_marker` |
| Tests | `test_knowledge_save_fixes.py` |

## Done (2026-06-09 session)

| Area | Change |
|------|--------|
| Check-in handler | `start_daily_checkin(self, …)` — PlanningBot method binding |
| Deploy safety | `vault_paths.yaml` excluded from rsync prod list |
| vault_paths materialize | locale-specific example only (no EN generic override on RU) |
| Server config | `ensure_repo_config.sh`: `PYTHONPATH`, wrong-locale replace via `vault_paths_locale` |
| Deploy noise | `resolve_shell_msg.py` joins `argv[3:]`; bootstrap uses compact python version |
| Check-in UX | Removed `**bold**` from check-in message keys (no `parse_mode` in handler) |
| Tests | `test_start_daily_checkin_bound_as_planning_bot_method` |

## P0 — regressions to watch

1. **`vault_paths` materialize** — fixed 2026-06-10: `materialize_locale` / `ensure_repo_config` no longer merge generic `vault_paths.yaml.example` (EN) over `vault_paths.ru.yaml.example` (was creating `100_Tasks` ghost dirs via `init_vault_layout`).
2. **Author `messages.ru.yaml`** — not in git; after example changes merge `checkin_*` keys manually on Mac + server.
3. **Partial deploy** — `planning_bot` only does not rsync `shared/`; ensure full deploy after shared changes.
4. **Markdown in planning messages** — many `planning.messages.*` still use `**` where handlers omit `parse_mode`; audit per handler or standardize `parse_mode=MarkdownV2`.

## P1 — architecture / hardcode

| # | Issue | Location | Target state |
|---|-------|----------|--------------|
| 1 | LLM numeric defaults in signatures | `shared/llm.py` `chat_with_tools(temperature=…)` uses `role_*` helpers but callers pass literals `0.3`, `0.7` | All from `config/agent/models.yaml` / `platform.yaml` only |
| 2 | Legacy menu routing | `shared/telegram/host/domain_dispatch.py`, `BTN_BULK_ON` string compares | `ui_capabilities.menu_actions` + `menu_dispatch` only |
| 3 | Domain string constants | `DOMAIN_KNOWLEDGE`, `if ui_mode != …` chains in host | Capability-driven reply specs |
| 4 | `shared/agent/router.py` | `default_timeout = 120` from dict default | `platform.yaml` single source |
| 5 | Planning LLM temps | `planning_llm_temperature("task_parsing", 0.3)` fallback literals | Remove numeric fallbacks; require YAML |
| 6 | Global `CAPS` env-style names | scattered `FEAT_*`, `DOMAIN_*` | OK as module ids; document in `ARCHITECTURE.md` |

## P2 — repo hygiene (maintainer vs OSS)

**Should NOT ship in OSS root** (author-only; target: `scripts/local/` + gitignore or separate private repo):

| Path | Notes |
|------|-------|
| `knowledge_bot/tools/*` | vault audits, retag, duplicates — 20+ scripts |
| `planning_bot/tools/*` | iphone sync, calendar, vault_maintenance |
| `finance_bot/tools/*` | tinkoff, reset_data, init_accounts |
| `scripts/setup/translate_domain_messages.py` | one-off i18n helper |
| `knowledge_bot/tools/apply_duplicates_resolution.py` | hardcoded timeout 120 |

**Keep in OSS:** `scripts/deploy.sh`, `obsidian_sync.sh`, `ensure_*`, `setup/`, `cron_routines.sh`.

## P3 — regular processes

| Process | Expected | Verify |
|---------|----------|--------|
| `unified_bot` | polling on VPS | `pgrep -f unified_bot.main` |
| `cron_routines.sh` | 01:00 MSK → routines history | crontab on server |
| `obsidian_sync.sh` | Mac LaunchAgent → rsync + charts | `check_sync_health.sh` |
| Daily check-in cron | 23:45 MSK APScheduler | `planning_bot.app.scheduling` |
| Finance schedulers | broker sync, reminders | finance startup log |

Document in `docs/DEPLOY_VPS.md` (partial — expand cron table).

## P4 — i18n / onboarding

| Item | Status |
|------|--------|
| Default EN examples | ✅ `messages.en.yaml.example`, `vault_paths.en.yaml.example` |
| RU materialize | ✅ `materialize_locale.py --refresh-vault-paths` |
| Onboarding skill | ✅ `.cursor/skills/obsidian-agent-onboarding/SKILL.md` |
| Author personalization | prompts interview → prod `.txt`; `vault_paths.yaml`; `capabilities.yaml` |
| `domain_messages` size | ⚠️ large generated files; EN/RU parity via examples + merge |

## P5 — polish / features

- Agent tool `get_daily_signals` for NL queries over signals history
- `signals_week.json` export for dashboards
- Morning block in check-in (separate 10:00 flow)
- Check-in: `parse_mode` policy doc (when Markdown vs plain)
- Onboarding: EN default kanban categories from `kanban_schema.en`

## Verification commands

```bash
AGENT_LOCALE=en ./scripts/setup.sh
./scripts/oa-python.sh scripts/setup/materialize_locale.py en
./scripts/oa-python.sh -m pytest \
  tests/test_no_cyrillic_in_py.py \
  tests/test_daily_checkin.py \
  tests/test_onboarding.py \
  tests/test_ui_bindings.py -q
```

## Non-goals

- Auto-migrate author Obsidian note titles (`🎯 Главный_Дашборд.md`).
- Ship prod prompts, personal vault, or author `vault_paths.yaml` in git.
- Force all users to Russian folder names.
