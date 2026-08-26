# Launch post draft (HN / Reddit / Obsidian community)

Copy, trim, and post when CI is green. Prefer a short screen recording or `assets/demo/demo.gif`
([capture notes](DEMO_CAPTURE.md)); until then link the repo + public gold only — do not ship a fake GIF.

## Title options

- Show HN: obsidian-agent – Telegram + Obsidian life OS with fail-closed modules
- I built a vault-native agent (tasks, notes, money) that refuses to leak disabled features
- Obsidian as system of record; Telegram as the sensor

## Body (short)

I got tired of AI chats that forget and vaults that stay stale when I’m away from the desk.

**obsidian-agent** is a single Telegram process over planning / knowledge / finance. The Obsidian vault is canonical. Capabilities are fail-closed: if a module or connector is off, it disappears from UI, tools, prompts, and sync — not just a hidden menu item.

Core install is Telegram + vault + any OpenAI-compatible LLM. Mac, broker APIs, and health pipes are optional connectors.

- Voice / photo / text capture with confirm-before-write for money
- Kanban as real markdown, not a bot todo list
- Optional health / calendar / broker connectors ([docs/CONNECTORS.md](CONNECTORS.md))
- EN + RU catalogs; Docker is runtime after bootstrap (not a fake one-click OS)

Repo: https://github.com/aeshef/obsidian-agent  
Public retrieval gold: `eval/gold/public_v0.yaml`

Happy to take issues on onboarding friction — `/setup` in Cursor or `./scripts/onboarding_wizard.sh`.

## Channels

1. Hacker News — Show HN
2. r/ObsidianMD
3. r/LocalLLaMA (agent + RAG angle; be honest: catalog RAG, embeddings on roadmap)
4. Obsidian Discord / Telegram communities (no spam — one thoughtful post)

## Do not

- Paste personal dashboards with real balances
- Claim “beats Notion” without the fail-closed / vault-native distinction
- Promise Docker = full life OS
