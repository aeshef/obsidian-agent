# Capabilities manifest

Declarative product profile: which Telegram domains, data connectors, and Mac sync steps are active. **No `capabilities.yaml`** (only in-memory defaults) or all flags `true` = full install (same behavior as before modularization). The `.example` file is not read at runtime — copy it via `setup_agent_config.sh` when you want a starting point.

## Setup

**Guided:** [ONBOARDING.md](ONBOARDING.md) or Cursor skill `.cursor/skills/obsidian-agent-onboarding`.

```bash
./scripts/setup_agent_config.sh   # copies other *.example.yaml; does **not** create capabilities.yaml
python3 scripts/apply_capabilities_profile.py --only-modules planning --write --patch-env  # any mix
python3 scripts/init_vault_layout.py
./scripts/install_mac_sync.sh     # LaunchAgent loads CAP_SYNC_* from capabilities
```

`config/agent/capabilities.yaml` is gitignored. The example in repo has no personal data.

## Sections

| Section | Purpose |
|---------|---------|
| `modules` | `finance`, `planning`, `knowledge` — host adapters, keyboards, routers, schedulers |
| `connectors` | Optional pipelines (badge, broker API, manual broker accounts, Apple Health, Gmail, calendar, Mac context, KB serendipity) |
| `sync.profile` | `auto` (infer), `full`, `finance_only`, `planning_light`, `planning_kanban`, `minimal` |
| `features` | Optional fine-grained flags (nutrition chart, broker IIS, planning cron jobs, …) — omitted keys inherit from modules/connectors |

Connectors also gate agent tools (`shared/capabilities/registry.py`) and finance scheduler jobs (broker sync, badge digests).

Broker API kind toggles: `features.broker_*` in capabilities and/or `accounts` in `finance_bot/config/broker_sync.yaml` (`provider: tinkoff|none`).

## Environment overrides

- `CAPABILITIES_PATH` — alternate YAML path (tests, CI)
- `CAPABILITIES_SYNC_PROFILE` — override `sync.profile`
- `CAP_MODULE_FINANCE`, `CAP_MODULE_PLANNING`, `CAP_MODULE_KNOWLEDGE` — `0`/`1`
- `CAP_CONNECTOR_<NAME>` — e.g. `CAP_CONNECTOR_BROKER_SYNC=0`

`scripts/obsidian_sync.sh` loads `CAP_SYNC_*` via `scripts/export_capabilities_env.py` (see `scripts/lib/capabilities.sh`).

## Sync step env vars

| Variable | obsidian_sync step |
|----------|-------------------|
| `CAP_SYNC_PLANNING_CHARTS` | Step 5 — task activity charts |
| `CAP_SYNC_CALENDAR` | Step 5c — calendar PNG |
| `CAP_SYNC_KB_MAINTENANCE` | Step 5b.2 — vault_daily_maintenance |
| `CAP_SYNC_VAULT_AUDIT_HEAVY` | Step 5b.3 — 700_ audit report |
| `CAP_SYNC_GMAIL_HEALTH` | Step 5b.4 — iphone_mail_sync |
| `CAP_SYNC_MAC_IPHONE` | Step 5b.4b — iphone_context_sync |
| `CAP_SYNC_NUTRITION` | Step 5d — nutrition chart |
| `CAP_SYNC_FINANCE_DASHBOARD` | Step 6 — finance.db + dashboard |

## Rsync folders (Mac sync)

Exported via `CAP_MODULE_*` (see `export_capabilities_env.py`):

| Folder | When synced |
|--------|-------------|
| `100_`, `200_`, `400_`, `600_` | `planning` module on |
| `300_` | any of finance / planning / knowledge |
| Knowledge subdir (`VAULT_REL_KNOWLEDGE`) | `knowledge` module on |

Broker UI/NLU (Tinkoff sync commands, invest menu) is hidden when `connectors.broker_sync` is off — see `shared/capabilities/finance_gates.py`.

## Examples

**Kanban only:**

```yaml
modules:
  finance: false
  planning: true
  knowledge: false
connectors:
  corporate_badge: false
  broker_sync: false
  manual_broker_accounts: false
  apple_health: false
  gmail_health_pipeline: false
  apple_calendar: false
  mac_context: false
  knowledge_serendipity: false
sync:
  profile: planning_kanban
```

CLI equivalent: `--only-modules planning --write`.

Still configure `.env`, `finance_bot/config/*`, and vault paths separately — the manifest does not store secrets or personal paths.

**Deploy:** `./scripts/deploy.sh --prod` runs one `unified_bot` process (legacy three bots only with `--legacy-bots`).

## Prod prompts (`*.txt`)

- Production uses `config/agent/prompts/<name>.txt` (gitignored).
- `*.example.txt` in git are templates only; stubs (all `#` lines) are not sent to the LLM.
- Wrap optional instructions:

```text
<!-- @cap broker -->
...
<!-- @/cap -->
```

Ids: modules (`planning`, `finance`), connectors (`broker_sync`, `gmail_health_pipeline`, …), features (`health_body_metrics`, …). Loaded via `shared/prompts.py` → `filter_prompt_capabilities`.

Dynamic supplement is **off by default** (`AGENT_PROMPT_DYNAMIC_SUPPLEMENT=0` in `.env.example`). Set to `1` only if prod `*.txt` lack `<!-- @cap -->` blocks. Prefer explicit `@cap` in prod prompts (`host_query`, `health_tools`, …).

## Runtime YAML (UI / domain strings)

`messages.{en,ru}.yaml` and `domain_messages.{en,ru}.yaml` use `load_runtime_config` (see [LOCALE.md](LOCALE.md)). Default `AGENT_LOCALE=en`. English domain strings merge over Russian until the EN catalog is fully translated.

### UI string gates (`config/ui_capabilities.yaml`)

Dot-paths map to capability specs (`finance.sync_broker_button: gate:broker`, `planning.auto_f317ab8f35: feature:planning_routines`, `any:broker,manual_broker`). Resolved in `shared/capabilities/ui_bindings.py` — `msg()` / `dmsg()` return `""` when off (no per-handler `cap=`).

`menu_detection` and `domain_routing` in the same file drive host menu routing (`shared/telegram/host/domain_dispatch.py`, `menu_detection.py`).

### Reply keyboard actions (`menu_actions`)

Under `menu_actions:` in `ui_capabilities.yaml.example`: maps reply-keyboard labels to handler action ids per domain (`planning`, `finance`, `knowledge`). Loaded by `shared/capabilities/menu_actions_config.py`; handlers live in `{bot}/menu_action_handlers.py` and `shared/telegram/reply_menu_dispatch.py`. Add a row in YAML + register the action id in the domain handler module — no new hardcoded label lists in Python.

Optional override: copy `ui_capabilities.yaml.example` → `ui_capabilities.yaml` (gitignored).

---

### Русский (кратко)

Строки UI и `menu_actions` — в `ui_capabilities.yaml.example` (локально `ui_capabilities.yaml`). Гейты через `ui_bindings.py`; кнопки reply-меню — декларативно в `menu_actions`, обработчики в `{bot}/menu_action_handlers.py`.

English: `messages.en.yaml` + `AGENT_LOCALE=en`.

## Onboarding smoke

```bash
python3 scripts/onboarding_smoke.py
python3 scripts/onboarding_smoke.py --verify-connectors
python3 scripts/onboarding_smoke.py --require-env
python3 scripts/onboarding_smoke.py --golden-planning
```

## Connectors (fine-grained)

| Connector | Gates |
|-----------|--------|
| `gmail_health_pipeline` | Gmail IMAP sync step (independent of `apple_health`) |
| `apple_health` | Health tools, iPhone sync |
| `features.health_body_metrics` | Weight/fat on nutrition chart |
| `features.health_nutrition_chart` | KBJU chart sync step |
| `domestic_bank_cards` | Card lines on finance balance chart |
| `broker_sync` + `broker_sync.yaml` `provider` | API sync (today: `tinkoff`) |
| `manual_broker_accounts` | Broker overview tool without API |

## Code map

- `shared/capabilities/profile.py` — load YAML + env
- `shared/capabilities/registry.py` — filter agent tools
- `shared/capabilities/sync_steps.py` — sync profile + shell export
- `shared/capabilities/hints.py` — LLM domain hints without disabled features
- `shared/capabilities/features.py` — fine-grained flags + planning/broker gates
- `shared/capabilities/planning_gates.py` — APScheduler job toggles
- `shared/capabilities/ui_bindings.py` — Telegram/domain string gates
- `shared/capabilities/menu_actions_config.py` — reply keyboard → action id
- `shared/setup/env_patch.py` — idempotent `.env` key hints (`--patch-env` on apply script)
- `shared/telegram/host/*` — adapters, bootstrap, domain dispatch
- `shared/telegram/reply_menu_dispatch.py` — menu action routing
