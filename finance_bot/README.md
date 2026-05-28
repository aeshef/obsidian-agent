# Finance domain

Part of [obsidian-agent](../README.md). **Prod:** `python -m unified_bot.main`.

| Topic | Where |
|-------|--------|
| Install & modules | [docs/ONBOARDING.md](../docs/ONBOARDING.md), [docs/CAPABILITIES.md](../docs/CAPABILITIES.md) |
| Agent tools | [docs/AGENT_PLATFORM.md](../docs/AGENT_PLATFORM.md) |
| Prompts | `finance_bot/config/prompts/*.example.txt` → local `*.txt` |
| NLU / LLM / categories | `*.yaml.example` → local `*.yaml` optional (`load_merged_config`) |
| Broker / accounts | `broker_sync.yaml.example`, `initial_accounts` (gitignored) |

**Features:** NLU transactions, voice, balances, plans, debts, investments, optional broker sync & meal badge.

**Layout:** `bot/` Telegram UI, `services/` DB & analytics, `config/` NLU & prompts.
