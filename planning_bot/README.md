# Planning domain

Part of [obsidian-agent](../README.md). **Prod:** `python -m unified_bot.main` (not `planning_bot.app.main`).

| Topic | Where |
|-------|--------|
| Install & modules | [docs/ONBOARDING.md](../docs/ONBOARDING.md), [docs/CAPABILITIES.md](../docs/CAPABILITIES.md) |
| Agent tools | [docs/AGENT_PLATFORM.md](../docs/AGENT_PLATFORM.md) |
| Prompts | `planning_bot/config/prompts/*.example.txt` → local `*.txt` |
| Vault paths | `config/vault_paths.yaml` (from example) |
| ASR | `planning_bot/config/asr_config.yaml.example` |

**Features:** kanban, goals, routines, reflection, calendar export, Mac/iPhone context, action logs, charts (via `obsidian_sync.sh` on Mac).

**Layout:** `app/` handlers, `services/` kanban & calendar, `tools/` sync helpers, `config/` prompts & schemas.
