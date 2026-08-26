# obsidian-agent — Cursor agent instructions

## Onboarding

Open **this folder** as the Cursor workspace (File → Open Folder → `obsidian-agent` / `Agent`).

In chat, run **`/setup`** (or type `@setup` skill). Do **not** paste the path to `SKILL.md` — that only makes the model summarize the doc.

If the workspace is the parent Obsidian vault, `/setup` is also at the vault root `.cursor/commands/setup.md`.

Full playbook: `.cursor/skills/obsidian-agent-onboarding/SKILL.md`

---

## Product architecture (do not regress)

This repo is the result of multi-iteration hardening. Treat these as hard constraints:

1. **Merged** — three working bots (planning / knowledge / finance) share one infrastructure; prod entry is `unified_bot`, domains remain libraries.
2. **Modular / fail-closed** — modules and connectors turn on/off via `capabilities.yaml`. Off = gone from UI, tools, prompts (`@cap`), and sync steps. Never reintroduce always-on features.
3. **Agentic** — no scenario hardcode in Python. User NL → agent loop (route → tools → verify). Cheap intents may skip the heavy model; do not replace the loop with if/else product logic.
4. **Config over code** — strings, numbers, paths, limits, scenarios live in YAML / platform config / prompts on disk. No new magic numbers or user-facing copy in `.py`.
5. **Prompts** — never embed prompt bodies in code. Git has `*.example.txt` (generic OSS). Prod `*.txt` are local/gitignored personalized overlays. Do not commit personal prompts or invent “demo personality” that looks like the author.
6. **No personal identity in git** — no names, employers, values, real balances, city-identifying vault paths, or private history. Public tree must stay anonymous/portable.
7. **Locale** — English-first catalogs; Russian via `AGENT_LOCALE` + examples/packages. When adding copy: update **both** EN and RU packages (or the right `messages.*.example`). Respect EN/RU vault path examples (`vault_paths.en` / `.ru`) — never hardcode one locale’s folder names.
8. **Shared / modular layout** — prefer `shared/` and domain packages over new god-files. Split carefully; do not dump one-off scripts into the public tree (use gitignored `scripts/maintainer/` / `docs/_maintainer/`).
9. **Mac ↔ VPS sync** — file/layout changes must stay compatible with `obsidian_sync` / deploy. Changing paths or authority on one side only will get overwritten. Think local + server together; prefer capabilities-gated sync steps.
10. **Naming** — connectors/docs stay OS-neutral where possible (`health_snapshots` alias, generic broker labels). Locale examples: neutral brands in EN; RU strings without leaking personal banks into defaults.

## Before editing

- Read existing patterns in the touched domain (`shared/`, `unified_bot/host/`, capabilities).
- Prefer extending YAML / prompts / capabilities over new Python branches.
- After config or path changes: consider deploy/rsync impact and both locales.
- Never commit `.env`, `capabilities.yaml`, prod prompts, `badge.yaml`, real vault data.
