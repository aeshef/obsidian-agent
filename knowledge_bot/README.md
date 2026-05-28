# Knowledge domain

Part of [obsidian-agent](../README.md). **Prod:** `python -m unified_bot.main`.

| Topic | Where |
|-------|--------|
| Install & modules | [docs/ONBOARDING.md](../docs/ONBOARDING.md), [docs/CAPABILITIES.md](../docs/CAPABILITIES.md) |
| Agent tools | [docs/AGENT_PLATFORM.md](../docs/AGENT_PLATFORM.md) |
| Prompts | `knowledge_bot/config/prompts/*.example.txt` → local `*.txt` |
| Vault folder name | `VAULT_REL_KNOWLEDGE` / `vault_paths.yaml` |

**Features:** ingest text/links/media, ASR, vision, tags, search & query, optional serendipity, vault maintenance (Mac sync step 5b).

**Layout:** `app/` bot & agent tools, `services/` extract/persist/routing, `tools/vault_daily_maintenance.py` (Mac sync; остальные audit/fix tools — author-only, не в git).
