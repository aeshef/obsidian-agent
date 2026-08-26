# Onboarding (modular install)

Build **any** combination of modules and connectors. Presets (`finance_only`, `planning_only`, …) are shortcuts, not the only path.

## Modules vs connectors

| Layer | Controls |
|-------|----------|
| **modules** | `finance`, `planning`, `knowledge` — Telegram domains, routers, schedulers |
| **connectors** | Badge, broker API, Apple Health, Gmail IMAP, calendar, Mac context, KB serendipity, manual broker accounts |
| **features** | Fine-grained flags (nutrition chart, broker IIS, planning cron jobs, …) |
| **sync.profile** | Mac `obsidian_sync.sh` steps; use `auto` to infer from modules/connectors |

## Cursor interactive setup (recommended)

1. **Cursor → Open Folder** → `obsidian-agent` repo root (directory with `unified_bot/`).  
   If the agent lives inside a vault (`…/Obsidian Vault/obsidian-agent`), either open that subfolder **or** use `/setup` from the vault root (copy `.cursor/commands/setup.md` from docs if missing).

2. In chat: **`/setup`** or **`@setup`** — not a path to `SKILL.md` (that only produces a summary).

Playbook executed by the operator: `.cursor/skills/obsidian-agent-onboarding/SKILL.md` (**Single-chat script**)

Interview CLI:

```bash
python3 scripts/onboarding_interview.py next          # next question (JSON)
python3 scripts/onboarding_interview.py answer ID '…' # save reply → slots + user_profile + initial_accounts
python3 finance_bot/scripts/apply_initial_accounts.py # seed SQLite balances (finance)
python3 scripts/onboarding_smoke.py --complete        # full done gate
```

## One-shot shell wizard

```bash
./scripts/onboarding_wizard.sh --playbook planning   # or finance | full
./scripts/onboarding_wizard.sh --modules knowledge --connectors --knowledge-serendipity
./scripts/onboarding_wizard.sh --dry-run --playbook finance
```

The wizard runs `apply_capabilities_profile`, locale/`vault_paths` materialization, then `init_vault_layout` (only folders for enabled modules), `ensure_bot_prompts`, and `onboarding_smoke.py`. Secrets: `python3 scripts/setup/env_tools.py set KEY 'value'` or use `/setup` in Cursor.

**Locale:** wizard calls `set-locale --refresh-vault-paths` so Russian installs get `100_Задачи`, not `100_Tasks`. Never copy `vault_paths.yaml.example` by hand.

## Examples

```bash
cp .env.example .env   # VAULT_PATH, TELEGRAM_UNIFIED_BOT_TOKEN, DEEPSEEK_API_KEY

# Kanban / tasks only (no health, finance, KB)
python3 scripts/apply_capabilities_profile.py --only-modules planning --write --patch-env

# Knowledge base only
python3 scripts/apply_capabilities_profile.py --only-modules knowledge --write --patch-env

# Finance + broker sync (csv or optional T-Invest)
python3 scripts/apply_capabilities_profile.py --only-modules finance --broker-sync --write --patch-env

python3 scripts/init_vault_layout.py
./scripts/setup.sh
# In Obsidian app: install Community plugins (see docs/OBSIDIAN_SETUP.md)
python3 scripts/install_obsidian_setup.py
./scripts/install_mac_sync.sh
```

Legacy preset names still work: `--preset finance_only`, `--preset planning_light`, etc.

## CLI flags

- `--only-modules planning finance` — enable listed modules only
- `--planning` / `--no-finance` — toggle one module
- `--broker-sync`, `--apple-health`, … — toggle connectors (see `--help`)
- `--sync-profile auto` (default) or `full`, `planning_kanban`, `finance_only`, …
- `--patch-env` — append missing `.env` keys (never overwrites values)
- `--setup-badge` — copy `badge.yaml.example` if needed

## Golden path: planning only (~15 min)

```bash
cp .env.example .env
# VAULT_PATH, TELEGRAM_UNIFIED_BOT_TOKEN, DEEPSEEK_API_KEY

python3 scripts/apply_capabilities_profile.py --only-modules planning --write --patch-env
python3 scripts/init_vault_layout.py
./scripts/setup.sh
# Obsidian app: Community plugins — docs/OBSIDIAN_SETUP.md
python3 scripts/install_obsidian_setup.py

python3 scripts/onboarding_smoke.py --golden-planning --agent-sanity
python3 scripts/onboarding_smoke.py --verify-all --require-env   # after each connector / at the end

export PYTHONPATH=.
python3 -m pytest tests/test_profile_matrix.py tests/test_ui_bindings.py -q
```

Telegram: `python -m unified_bot.main` → mode **Planning** → «Мои задачи».

## Golden path: finance only (~20 min)

```bash
cp .env.example .env
# VAULT_PATH, TELEGRAM_UNIFIED_BOT_TOKEN, DEEPSEEK_API_KEY

python3 scripts/apply_capabilities_profile.py --only-modules finance --write --patch-env
python3 scripts/setup/materialize_locale.py "${AGENT_LOCALE:-en}"
bash scripts/ensure_repo_config.sh
python3 scripts/init_vault_layout.py
./scripts/setup.sh
bash scripts/ensure_bot_prompts.sh

python3 scripts/onboarding_smoke.py --golden-finance --agent-sanity
python3 scripts/onboarding_smoke.py --verify-all --require-env
```

Telegram: `python -m unified_bot.main` → mode **Finance** → balance / last ops. Broker API and corporate badge are optional (`--broker-sync`, `--corporate-badge`); UI gates live in `config/ui_capabilities.yaml.example`.

## Vault layout (not fixed numbering)

Folder names live in `config/vault_paths.yaml` (materialized from `vault_paths.en.yaml.example` or `vault_paths.ru.yaml.example` via `AGENT_LOCALE`). Rename `folders.tasks`, `folders.goals`, etc. to match **your** Obsidian tree — Python reads segments only from YAML. `init_vault_layout.py` creates missing dirs under `VAULT_PATH`.

## Rebrand connectors (broker / meal badge)

| What | Where |
|------|--------|
| Broker API label | `config/messages.ru.yaml` → `finance.sync_broker_button`, `inline_invest_*` |
| Broker provider | `finance_bot/config/broker_sync.yaml` → `provider: csv\|tinkoff\|none` |
| Account display names | `broker_sync.yaml` → `accounts`, `display_names` |
| Meal badge | `finance_bot/config/badge.yaml` + `messages.ru` → `finance.menu.badge` |
| UI capability gates + reply menu | `config/ui_capabilities.yaml` (`strings`, `menu_actions`; optional override of `.example`) |

English UI: `cp config/messages.en.yaml.example config/messages.en.yaml`, set `AGENT_LOCALE=en` in `.env`.

## Author install (unchanged)

Author full install: omit `capabilities.yaml` and set `OBSIDIAN_AGENT_FULL_INSTALL=1`. Clones: always `--write` a profile (or accept OSS starter).

See [CAPABILITIES.md](CAPABILITIES.md).
