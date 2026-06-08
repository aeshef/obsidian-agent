# obsidian-agent

[![CI](https://github.com/aeshef/obsidian-agent/actions/workflows/ci.yml/badge.svg)](https://github.com/aeshef/obsidian-agent/actions/workflows/ci.yml)

**Telegram is the inbox. Obsidian is the system of record.**

Capture tasks, notes, and money from chat (voice, text, media). The bot writes **markdown, JSON, and SQLite** into your vault. You keep editing in Obsidian; the bot handles fast input, NLU, search, charts, and optional 24/7 hosting.

![obsidian-agent](assets/banner.png)

---

## Why this exists

| Problem | What obsidian-agent does |
|--------|---------------------------|
| Ideas die while you open Obsidian | Telegram as a always-on capture surface |
| Life ops split across apps | One **unified bot** with pluggable domains |
| You want a server, but the vault lives on your Mac | Optional **rsync** — sync only folders you enabled |
| Not everyone needs health, broker, or meal benefits | **Capabilities manifest** — off means gone from UI, agent tools, and sync |

---

## What’s different

- **Vault-native** — Kanban, goals, knowledge notes, and `finance.db` live under *your* tree; folder names come from `config/vault_paths.yaml`, not hardcoded paths in Python.
- **Three domains, one process** — `planning`, `knowledge`, `finance` in a single `unified_bot` with classic Telegram handlers *and* a free-text **agent platform** (route domain → intent → tools).
- **Real modularity** — `config/agent/capabilities.yaml` toggles modules and connectors. Disabled features don’t leak into menus, LLM hints, or Mac sync steps.
- **Natural-language finance** — Batch expenses/income/transfers from plain text; confirm in chat before write.
- **Knowledge pipeline** — Text, voice (ASR), images, PDFs, links → tagged notes with wikilinks and RAG search.
- **Declarative UI** — Telegram labels and reply-keyboard routing live in `config/ui_capabilities.yaml.example` (`strings`, `menu_actions`), not scattered string checks in handlers.
- **OSS-first locale** — Default `AGENT_LOCALE=en`; Russian UI via `env_tools.py set-locale ru`. User-facing copy stays in YAML, not in `.py`.

---

## Quick start

**Requirements:** Python 3.9+, an Obsidian vault path, a [Telegram bot token](https://t.me/BotFather), and a [DeepSeek API key](https://platform.deepseek.com/) (planning + finance NLU; knowledge may also use OpenRouter for vision).

### Option A — Guided setup in Cursor (recommended)

1. Clone and open the repo in **Cursor**.
2. Start a chat and ask to **onboard obsidian-agent** — the skill at `.cursor/skills/obsidian-agent-onboarding` runs the wizard: pick modules/connectors, fill `.env` safely, materialize configs, scaffold prompts, smoke tests.
3. Run the bot:

```bash
export PYTHONPATH=.
python -m unified_bot.main
```

The skill never commits secrets or prod prompts; it follows the same steps as the CLI below.

### Option B — CLI wizard

```bash
git clone https://github.com/aeshef/obsidian-agent.git
cd obsidian-agent
cp .env.example .env
./scripts/setup.sh

# Pick a profile (planning | finance | full) or custom modules:
./scripts/onboarding_wizard.sh --playbook planning
# or: python3 scripts/apply_capabilities_profile.py --only-modules finance --write --patch-env

python3 scripts/init_vault_layout.py
python3 scripts/onboarding_smoke.py --golden-planning   # or --golden-finance

export PYTHONPATH=.
python -m unified_bot.main
```

Set at minimum in `.env` (or via `python3 scripts/setup/env_tools.py set KEY value`):

| Variable | Purpose |
|----------|---------|
| `VAULT_PATH` | Absolute path to your Obsidian vault |
| `TELEGRAM_UNIFIED_BOT_TOKEN` | Bot token from BotFather |
| `DEEPSEEK_API_KEY` | LLM for planning, finance NLU, agent routing |

**Next steps:** [docs/SETUP.md](docs/SETUP.md) (deploy, Mac sync), [docs/ONBOARDING.md](docs/ONBOARDING.md) (modules & smoke), [docs/PROMPTS_ONBOARDING.md](docs/PROMPTS_ONBOARDING.md) (personalize NLU prompts).

---

## Domains (mix and match)

| Module | You get |
|--------|---------|
| **planning** | Kanban tasks, goals, routines, weekly reflection, optional calendar & health context |
| **knowledge** | Ingest → tag → link → search your note corpus (text, voice, media, URLs) |
| **finance** | NLU transactions, dashboards, debts, optional broker API or manual investment accounts |

Turn modules and connectors on/off: [docs/CAPABILITIES.md](docs/CAPABILITIES.md).

---

## Example phrases

Neutral examples — swap amounts, names, and accounts for yours:

| You send | What happens |
|----------|----------------|
| `Add task: ship docs by Friday` | Kanban note + action log in vault |
| `What's in progress for project Alpha?` | Agent queries kanban + note search |
| `Spent 24 on coffee, main card` | NLU → row in `finance.db` |
| `How much on food this month?` | Finance summary (and investments if broker connector is on) |
| `Save this link about Rust` | Knowledge ingest with tags |
| `Find notes about hiking` | RAG answer grounded in vault files |

Pin a domain with the reply keyboard, or leave **Auto** and let the host router pick.

---

## How it fits together

```
Telegram  →  unified_bot  →  vault (markdown / JSON / SQLite)
                ↑
         shared/agent (tools, memory, routing)
                ↑
    planning_bot · knowledge_bot · finance_bot  (domain logic)

Optional: Mac obsidian_sync.sh  ⇄  VPS (24/7 bot + cron maintenance)
```

Architecture details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · Agent platform: [docs/AGENT_PLATFORM.md](docs/AGENT_PLATFORM.md)

---

## Repository map

```
obsidian-agent/
├── unified_bot/          # production entrypoint
├── shared/               # agent platform, LLM, capabilities, telegram host
├── planning_bot/         # tasks, goals, routines
├── knowledge_bot/        # ingest, tags, query
├── finance_bot/          # NLU, dashboards, scheduler
├── config/               # messages, vault_paths, ui_capabilities (*.example → local)
├── scripts/              # setup, deploy, obsidian_sync, onboarding CLI
└── docs/                 # full documentation index
```

---

## Documentation

| Doc | Topic |
|-----|--------|
| [docs/SETUP.md](docs/SETUP.md) | Install, deploy, Mac ↔ server sync |
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | Modules, connectors, golden paths |
| [docs/CAPABILITIES.md](docs/CAPABILITIES.md) | Manifest, sync steps, UI gates |
| [docs/PROMPTS_ONBOARDING.md](docs/PROMPTS_ONBOARDING.md) | Prompt tiers & personalization |
| [docs/LOCALE.md](docs/LOCALE.md) | `AGENT_LOCALE` (EN / RU) |
| [docs/ENV_REFERENCE.md](docs/ENV_REFERENCE.md) | Environment variables |
| [docs/TESTING.md](docs/TESTING.md) | pytest & CI |
| [CONTRIBUTING.md](CONTRIBUTING.md) | How to contribute |

---

## Development

```bash
./scripts/run_tests.sh -q
```

CI runs on push/PR: compile, smoke imports, pytest, capabilities/onboarding guards — see [.github/workflows/ci.yml](.github/workflows/ci.yml).

---

## License

MIT — see [LICENSE](LICENSE).

---

## Русский (кратко)

**obsidian-agent** — единый Telegram-бот, который пишет в ваш Obsidian vault: задачи, база знаний и финансы. Модули и коннекторы включаются декларативно; выключенное не попадает в UI, tools и sync.

**Установка:** откройте репозиторий в **Cursor** и пройдите онбординг (скилл `.cursor/skills/obsidian-agent-onboarding`) **или** `./scripts/setup.sh` + `./scripts/onboarding_wizard.sh`. Подробности — [docs/SETUP.md](docs/SETUP.md), [docs/ONBOARDING.md](docs/ONBOARDING.md).

**Язык интерфейса:** по умолчанию английский; русский: `python3 scripts/setup/env_tools.py set-locale ru` ([docs/LOCALE.md](docs/LOCALE.md)).

Полный индекс документации: [docs/README.md](docs/README.md).
