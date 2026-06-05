# Onboarding (modular install)

Build **any** combination of modules and connectors. Presets (`finance_only`, `planning_only`, …) are shortcuts, not the only path.

## Modules vs connectors

| Layer | Controls |
|-------|----------|
| **modules** | `finance`, `planning`, `knowledge` — Telegram domains, routers, schedulers |
| **connectors** | Badge, broker API, Apple Health, Gmail IMAP, calendar, Mac context, KB serendipity, manual broker accounts |
| **features** | Fine-grained flags (nutrition chart, broker IIS, planning cron jobs, …) |
| **sync.profile** | Mac `obsidian_sync.sh` steps; use `auto` to infer from modules/connectors |

## One-shot wizard (recommended for new clones)

```bash
./scripts/onboarding_wizard.sh --playbook planning   # or finance | full
./scripts/onboarding_wizard.sh --modules knowledge --connectors --knowledge-serendipity
./scripts/onboarding_wizard.sh --dry-run --playbook finance
```

The wizard runs `apply_capabilities_profile`, `init_vault_layout`, `ensure_bot_prompts`, and `onboarding_smoke.py`. Secrets still require `python3 scripts/setup/env_tools.py set KEY 'value'`. Full interactive flow: Cursor skill `.cursor/skills/obsidian-agent-onboarding/SKILL.md`.

**Author machine:** use `AGENT_LOCALE=ru` in `.env` before the wizard so `vault_paths.yaml` keeps your Cyrillic folder names (`100_Задачи`, not `100_Tasks`).

## Examples

```bash
cp .env.example .env   # VAULT_PATH, TELEGRAM_UNIFIED_BOT_TOKEN, DEEPSEEK_API_KEY

# Kanban / tasks only (no health, finance, KB)
python3 scripts/apply_capabilities_profile.py --only-modules planning --write --patch-env

# Knowledge base only
python3 scripts/apply_capabilities_profile.py --only-modules knowledge --write --patch-env

# Finance + Tinkoff API sync
python3 scripts/apply_capabilities_profile.py --only-modules finance --broker-sync --write --patch-env

python3 scripts/init_vault_layout.py
./scripts/setup.sh
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

## Rebrand connectors (examples use Tinkoff / corporate badge)

| What | Where |
|------|--------|
| Broker API label | `config/messages.ru.yaml` → `finance.sync_broker_button`, `inline_invest_*` |
| Broker provider | `finance_bot/config/broker_sync.yaml` → `provider: tinkoff\|none` |
| Account display names | `broker_sync.yaml` → `accounts`, `display_names` |
| Meal badge | `finance_bot/config/badge.yaml` + `messages.ru` → `finance.menu.badge` |
| UI capability gates | `config/ui_capabilities.yaml` (optional override of `.example`) |

English UI: `cp config/messages.en.yaml.example config/messages.en.yaml`, set `AGENT_LOCALE=en` in `.env`.

## Author install (unchanged)

Do **not** run `apply_capabilities_profile.py --write`. Omit `capabilities.yaml` for the full product.

See [CAPABILITIES.md](CAPABILITIES.md).
