# Repository goals audit — 2026-06-08

Scope: full iteration after hygiene fixes (`52a485b` + this commit).  
**Prod prompts:** only `*.example.txt` in git; local `*.txt` gitignored — never commit.

---

## Goals (author checklist)

| Goal | Target |
|------|--------|
| Unified | Single `unified_bot` process, shared agent loop |
| Modular | `capabilities.yaml` + `CAP_MODULE_*` / `CAP_SYNC_*` |
| Agentic | NL → router → tools; no scenario hardcode in handlers |
| Config-driven | Paths, temps, UI strings, prompts in YAML/txt files |
| OSS-safe | No PII in commits; maintainer scripts not in git |
| i18n | `AGENT_LOCALE=en` default; RU via `materialize_locale` |
| Onboarding | Skill + wizard → env + personalized prompts locally |

---

## Fixed this iteration (2026-06-08)

| Area | Change |
|------|--------|
| LaunchAgent | Duplicate `com.example.obsidian-sync` plist removed; `install_launchagent.sh` deletes legacy plists |
| `vault_paths` export | finance venv first; shell YAML fallback; wrapper pre-export |
| `add_ids` watcher | Correct vault path + venv python (no resolve→homebrew) |
| **Locale defaults** | `onboarding_wizard`, `deploy`, `run_tests`, `conftest` default **`en`** (author keeps `ru` in `.env`) |
| **Wizard order** | `materialize_locale` **before** `init_vault_layout`; locale-specific `vault_paths.*.yaml.example` |
| **seed_planning_prompts** | Seeds from `*.example.txt` only — no inline RU prompts in Python |
| **Shell Cyrillic paths** | `obsidian_sync.sh`, finance scripts use `VAULT_*` exports from `vault_paths_shell.py` |
| **vault_paths examples** | Added `chart_calendar_week_png`, `finance.chart_daily_categories_png` |
| **Maintainer tools** | `analyze_vault_report.py`, `repair_action_log_format.py`, `rename_action_snapshots.py` **removed from git** (stay local via `.gitignore`) |
| **recommendations.py** | `planning_llm_temperature("routines_recommendations")` |
| **Cron hygiene** | `_cron_common.sh` prefers `finance_bot/.venv`; `cron_routines.sh` logs OK/FAIL |
| **Tests** | `jinja2` in finance requirements; `test_mac_snapshots_range` skips sparse vault data |

---

## Regular processes — status 2026-06-08

| Process | Status |
|---------|--------|
| `obsidian_sync` LaunchAgent | OK — `last_sync_ok` fresh, exit 0 |
| Server `unified_bot` | UP |
| Server `kanban_monitor` | OK — every 2 min |
| Server `maintenance` (sync step 3) | 6/6 — IDs, sort, calendar, context |
| Server `routines` cron | OK — `📅 Сегодня.md` updated 01:00 |
| Mac `add_ids` watcher | OK — exit 0 after plist fix |
| Charts / finance / KB maintenance markers | Today in `health_report.md` |

**Not blocking:** VPS disk 87% (cleanup deferred). Gmail IMAP only on Mac.

---

## P0 — none

- Prod `*.txt` prompts not in git (`test_no_tracked_prod_prompt_txt_in_git`)
- Python prod code: vault paths via `vault_paths_config` / `VaultPaths`
- `chat_with_tools`: temps/timeouts from `models.yaml` via `ModelRouter`

---

## P1 — closed (2026-06-08)

| Item | Change |
|------|--------|
| **obsidian_sync step 5c** | `scripts.obsidian_sync.step_5c` / `step_5c_fail` via `sh_msg` |
| **Vault path Cyrillic in rsync excludes** | `VAULT_DASH_*`, `VAULT_FILE_*`, `VAULT_FIN_CHART_*` from `vault_paths_shell.py` |

## Fixed P2 (2026-06-08, after `225053f`)

| Item | Change |
|------|--------|
| **Shell log i18n** | `scripts/lib/sh_msg.sh` + `scripts.*` in `messages.{en,ru}.yaml.example`; `deploy.sh`, `obsidian_sync.sh`, `common.sh` |
| **vision temperature** | `knowledge_extract.vision_openrouter_temperature` in `platform.yaml.example` |
| **auto_dispatch** | Handler registry in `auto_routing.py` |
| **EN dmsg gaps** | Fixed `planning.logs_dir_*` YAML nesting + `calendar_*` chat keys in both `.example` files |
| **BTN_* if-chains** | `knowledge_bot/app/menu_dispatch.py`; `knowledge_dispatch`, `modes`, `menu_detection` |
| **setup.sh shell i18n** | `scripts.setup` / `deploy_agent` / `bootstrap` keys; `setup.sh`, `bootstrap_python.sh`, `deploy_agent.sh` |
| **domain_dispatch handlers** | `domain_handlers.py` + `DOMAIN_HANDLERS`; thin loop in `domain_dispatch.py` |
| **menu dispatch unify** | `shared/telegram/reply_menu_dispatch.py` — finance / planning / knowledge |
| **materialize_locale merge** | Deep-merge missing keys into existing `domain_messages.*.yaml` |
| **test_ocr_profile** | Mock `pytesseract` so Tesseract path is deterministic |

| Item | Change |
|------|--------|
| **ASR / extract timeouts** | `shared/platform_timeouts.py` + `platform.yaml.example` sections `asr`, `knowledge_extract`, `llm_reachable` |
| **DOMAIN_* dispatch** | `domain_dispatch.py` → config order via `ui_capabilities.domain_routing` |
| **Dead media timeouts** | Removed unused `timeout=` on `fetch_telegram_file_bytes` |
| **routines_recommendations** | Added to `planning_llm` in `platform.yaml.example` |

---

## P2 — improvements

- `ui_bindings.yaml` for menu detection (replace remaining domain-specific submenu branches gradually)
- OSS checklist doc: single ordered page mirroring wizard phases 0–8
- `git filter-repo` if public history must be PII-free
- Remaining setup section headers (`=== venv ===`, etc.) — optional `scripts.setup` keys

---

## Maintainer scripts policy

**In git (OSS):** deploy, onboarding, `export_*`, prod sync (`calendar_sync`, `vault_maintenance`, `map_missing_goals`), chart builders.

**Gitignored (author/local):** `scripts/maintainer/`, `analyze_vault_*.py`, `repair_*.py`, `reprocess_notes.py`, `retag_notes.py`, `audit_*.py`, `setup_watcher.sh` (LaunchAgent installer).

**Optional local:** `analyze_vault_report.py` — `obsidian_sync` step 5b.3 runs only if file exists in working tree.

---

## OSS onboarding — canonical order

1. `cp .env.example .env`
2. `./scripts/onboarding_wizard.sh --playbook planning` (or `--locale ru` for Cyrillic vault)
3. `python3 scripts/setup/env_tools.py set …` (secrets)
4. `./scripts/onboarding_smoke.py --require-env`
5. Optional Mac: `./scripts/install_launchagent.sh`, `./scripts/install_mac_sync.sh`

Author machine: set `AGENT_LOCALE=ru` in `.env` **before** wizard so `vault_paths` stays Cyrillic.

---

## Commit policy (unchanged)

| Never commit | Safe in git |
|--------------|-------------|
| `config/**/prompts/*.txt` (prod) | `*.example.txt` |
| `domain_messages.yaml`, `messages.ru.yaml` | `*.yaml.example` |
| `.env`, `CHAT_ID.txt`, `vault_paths.yaml` (author) | `vault_paths.{en,ru}.yaml.example` |
| Maintainer audit/repair tools | `vault_daily_maintenance.py`, prod cron tools |

---

## Regression guard

```bash
./scripts/run_tests.sh          # AGENT_LOCALE=en default; CI sets ru explicitly
git ls-files '**/prompts/*.txt' # only *.example.txt
```

Do not revert: unified agent loop, capabilities profile, `pdmsg`/`dmsg`, action log format tests, keyboard CAP gates.
