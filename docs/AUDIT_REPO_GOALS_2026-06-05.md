# Repository goals audit — 2026-06-05

Scope: `800_Автоматизация/Agent` monorepo vs. target architecture (unified / modular / agent / config-driven / i18n / OSS-safe).

**Prod prompts:** only `*.example.txt` in git; local `*.txt` is gitignored and must not be committed.

---

## Fixed in this iteration (commit pending)

| Area | Fix |
|------|-----|
| Action logs | `_loose_json_block_re` no longer matches valid entries → repair stops on every append; collapse `\n{3,}` |
| Calendar sync | `_reconcile_existing()` drops phantom future slots; removed `_dedupe_same_time_slot` (conflicts visible) |
| LLM router | `ModelRouter` reads `temperature`, `timeout_sec`, `tool_choice` from `config/agent/models.yaml` |
| Prompt policy | `llm_context/*.example.txt` → `generic_en_prefixes` in `prompt_manifest.yaml.example` |
| Platform | `planning_calendar.sync_horizon_days` in `platform.yaml.example` |

**Post-deploy (vault, not git):** run once on server + local:

```bash
python3 planning_bot/tools/repair_action_log_format.py --month 2026-06
python3 planning_bot/tools/repair_action_log_format.py --remote --month 2026-06
python3 planning_bot/tools/calendar_sync.py
```

---

## P0 — was broken

1. **Action log repair loop** — every kanban move triggered `Repaired 1792+ glued entries`; file grew to 58k lines (90% blanks). Parser still worked; UX and disk cost broken.
2. **Calendar phantom events** — additive `_merge()` kept cancelled/moved iPhone events; agent showed fake slots (16:05, 18–21 school).
3. **CI prompt policy** — 40 `llm_context/*.example.txt` treated as personalized stubs → tests fail.

---

## P1 — open (next iterations)

### Architecture / no hardcode

| Item | Location | Notes |
|------|----------|-------|
| Legacy menu if-chains | `shared/telegram/host/router.py`, `planning_bot/app/handlers/commands.py` | KB bulk buttons, finance/planning menus before agent path |
| `tool_choice` first-iter policy | `shared/agent/core.py` `_DOMAINS_REQUIRE_TOOLS_FIRST` | Domain set in code, not YAML |
| Duplicate LLM client | `planning_bot/core/llm.py` | Temps 0.3/0.7/0.8 hardcoded; migrate to `shared.llm` + `platform.yaml` `planning_llm` |
| `shared/llm.py` signature defaults | `chat_json` temp 0.1, various timeouts | Callers should pass router/config values |
| Finance LLM config dead | `finance_bot/config/llm_config.yaml.example` | Not wired into `finance_bot/bot/llm.py` |
| Cyrillic sync defaults | `scripts/obsidian_sync.sh` vault folder fallbacks | Should be env/`vault_paths.yaml` only |

### Git hygiene

| Item | Action |
|------|--------|
| `scripts/public_release_mailmap.txt` | `git rm --cached` (content sanitized; policy = not in index) |
| `scripts/public_release_filter_replacements.txt` | same |

### Onboarding / universal repo

| Item | Status |
|------|--------|
| `obsidian-agent-onboarding` skill | Should fill `prompt_manifest` personalized stubs, `.env`, prod `*.txt` |
| `ensure_bot_prompts.sh --warn-stubs` | Works with tier manifest |
| Capabilities profile | `CAP_MODULE_*` enables partial installs |
| Locale | `AGENT_LOCALE=en` default; `messages.*.yaml` + `domain_messages.*` local |

---

## P2 — improvements

- Config-driven host menu dispatch table (replace `is_*_menu()` chains).
- `get_calendar` tool: surface `meta.txt_last_parsed` + stale warning in output.
- `planning_bot/core/llm.py` deprecation path documented in `ARCHITECTURE.md`.
- LaunchAgent interval from `platform.yaml` / env, not plist hardcode.
- Wire `finance_bot` NLU temps from `llm_config.yaml`.

---

## What is OK (do not regress)

| Goal | Evidence |
|------|----------|
| Unified agent loop | `shared/agent/core.py` `run_agent`, `AgentApp`, domain adapters |
| Modular bots | `unified_bot`, per-bot entrypoints, capabilities profile |
| No prod prompts in git | `test_no_tracked_prod_prompt_txt_in_git` |
| Maintainer scripts out of git | `scripts/maintainer/`, `deepseek_audit_*`, `patch_all_scripts.py` gitignored |
| i18n EN default | `shared/locale.py`, `messages.en.yaml.example`, `pdmsg`/`dmsg` |
| Action log format | Canonical via `action_log_format.py`; tests green |
| Regular processes | `obsidian_sync.sh` (calendar 5c, charts 5), server crontab examples, `calendar_sync.py` |
| PII in commits | Scrubbed; `CHAT_ID.txt`, `domain_messages.yaml`, prod YAML gitignored |
| Recent agent fixes | Kanban category enum in tools, activity log dedup, finance insight pace facts |

---

## Regular process checklist

| Process | Mac | VPS |
|---------|-----|-----|
| `obsidian_sync` LaunchAgent | `launchctl list \| grep obsidian` | N/A |
| Vault pull/push | rsync in `obsidian_sync.sh` | `/root/obsidian-vault` |
| `calendar_sync` | step 5c daily + txt mtime | reads synced JSON |
| Action logs | pull `Логи/` from server | bot writes `ACTION_LOGS_DIR` |
| `unified_bot` | N/A | `deploy.sh --prod --restart-unified` |
| Planning cron | N/A | `install_planning_crontab.sh` |

---

## Commit policy reminder

- **Never commit:** `*.txt` prompts (except `*.example.txt`), `domain_messages.yaml`, `messages.ru.yaml`, `.env`, `CHAT_ID.txt`, maintainer/audit one-offs.
- **Safe in git:** `*.example.txt`, `*.yaml.example`, neutral EN structural templates (`llm_context/`).
- **User personalization:** prod copies + onboarding skill fill stubs locally.
