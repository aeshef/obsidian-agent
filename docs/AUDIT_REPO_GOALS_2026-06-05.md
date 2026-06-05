# Repository goals audit — 2026-06-05

Scope: `800_Автоматизация/Agent` monorepo vs. target architecture (unified / modular / agent / config-driven / i18n / OSS-safe).

**Prod prompts:** only `*.example.txt` in git; local `*.txt` is gitignored and must not be committed.

---

## Fixed (9b22d81 + follow-up)

| Area | Fix |
|------|-----|
| Action logs | `_loose_json_block_re` no longer matches valid entries → repair stops on every append; collapse `\n{3,}` |
| Calendar sync | `_reconcile_existing()` drops phantom future slots; removed `_dedupe_same_time_slot` (conflicts visible) |
| LLM router | `ModelRouter` reads `temperature`, `timeout_sec`, `tool_choice` from `config/agent/models.yaml` |
| Prompt policy | `llm_context/*.example.txt` → `generic_en_prefixes` in `prompt_manifest.yaml.example` |
| Platform | `planning_calendar.sync_horizon_days` in `platform.yaml.example` |
| Menu dispatch | `domain_dispatch.py` + `menu_dispatch.py` — host/planning if-chains extracted |
| tool_choice | `routing.yaml` → `agent.tools_first_iter_domains` |
| Finance LLM | `llm_params.py` wires `llm_config.yaml` temps/timeouts/max_tokens |
| Planning LLM | `llm_params.py` + `platform.yaml` `planning_llm.*` |
| obsidian_sync | EN fallbacks via `vault_paths_defaults.sh`; vault detect via `.obsidian` |

**Mac sync:** `com.aeshef.obsidian-sync` is loaded (300s interval). False P0 from earlier grep.

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

## P1 — done (8d8029c + follow-up)

| Item | Status |
|------|--------|
| `planning_bot/core/llm_domain.py` | Domain methods extracted; `llm.py` thin facade |
| CAP keyboards/inline | `ui_capabilities.yaml` + `compact_keyboard_rows`, `test_keyboard_cap_gates.py` |
| `scripts/onboarding_wizard.sh` | One-shot over onboarding skill |
| `analyze_vault_report.py` | EN refactor; paths from `vault_paths.yaml` |
| `calendar_charts.py` | Lazy `pdmsg()` at runtime (fixes EN filenames on RU vault) |
| Onboarding docs | `ONBOARDING.md` + skill link wizard |

### Git hygiene

| Item | Status |
|------|--------|
| `public_release_*` in index | Removed in `9b22d81` |

### Onboarding / universal repo

| Item | Status |
|------|--------|
| `obsidian-agent-onboarding` skill | Should fill `prompt_manifest` personalized stubs, `.env`, prod `*.txt` |
| `ensure_bot_prompts.sh --warn-stubs` | Works with tier manifest |
| Capabilities profile | `CAP_MODULE_*` enables partial installs |
| Locale | `AGENT_LOCALE=en` default; `messages.*.yaml` + `domain_messages.*` local |

---

## P2 — improvements

- `ui_bindings.yaml` for menu detection.
- `planning_bot/core/llm.py` deprecation in `ARCHITECTURE.md`.
- Onboarding skill: full wizard for personalized prompts + `.env`.
- Capabilities: hide disabled-module keyboard buttons consistently.
- Git history filter-repo if public OSS needs zero PII in old commits.

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
