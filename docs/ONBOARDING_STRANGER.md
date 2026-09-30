# Stranger onboarding (<30 minutes)

You cloned the repo and have never seen this codebase. This page is the **shortest reliable path** to a working Telegram bot.

## Choose your path

| Path | Time | Best for |
|------|------|----------|
| **Cursor `/setup`** | 20–30 min | Recommended — operator runs commands, one question per message |
| **CLI wizard `--fast`** | 15–20 min automated + 10 min secrets/bot | Terminal-only, planning or finance |
| **DIY** | 30–45 min | You read [ONBOARDING.md](ONBOARDING.md) and run steps yourself |

## Prerequisites (5 min)

1. **macOS or Linux** with Python 3.10+ and git
2. **Obsidian vault** folder on disk (can be empty)
3. **Telegram** — create a bot via [@BotFather](https://t.me/BotFather) (`/newbot`)
4. **LLM API key** — [DeepSeek](https://platform.deepseek.com) or any OpenAI-compatible provider

## Fastest path: Cursor `/setup`

```bash
git clone https://github.com/aeshef/obsidian-agent.git
cd obsidian-agent
```

1. Open the **repo root** in Cursor (folder with `unified_bot/`)
2. Chat: **`/setup`**
3. Answer: playbook (**planning** is fastest) + locale
4. Paste **VAULT_PATH** when asked (drag folder into terminal)
5. Answer intro interview (or say “use defaults” — operator runs `apply-intro-defaults`)
6. Paste **Telegram token** and **LLM key** when asked
7. Start bot → test in Telegram → operator runs `confirm-bot`
8. Pick deploy target (VPS recommended for 24/7)

**Progress anytime:**

```bash
./scripts/oa-python.sh scripts/onboarding_status.py
```

## Fastest CLI: wizard + defaults

```bash
git clone https://github.com/aeshef/obsidian-agent.git
cd obsidian-agent
cp .env.example .env

./scripts/onboarding_wizard.sh --playbook planning --fast --locale en
# TTY: paste VAULT_PATH, Telegram token, LLM key when prompted

./scripts/run_unified_bot.sh
# Telegram → /start → send a test message
./scripts/oa-python.sh scripts/onboarding_interview.py confirm-bot
```

Finish finalize questions in `/setup` or:

```bash
./scripts/oa-python.sh scripts/onboarding_interview.py next   # deploy_target, etc.
./scripts/oa-python.sh scripts/onboarding_smoke.py --verify-all --complete --golden-planning
```

## Phase checklist (contract)

Same order in `config/agent/bootstrap_checklist.yaml.example`:

| # | Phase | You do |
|---|--------|--------|
| 1 | repo + `.env` | clone, `cp .env.example .env` |
| 2 | venv bootstrap | `./scripts/setup.sh` (wizard runs this) |
| 3 | **VAULT_PATH** | **before** `init_vault_layout` |
| 4 | capabilities | playbook → `capabilities.yaml` |
| 5 | locale | `vault_paths.yaml` for en/ru |
| 6 | intro interview | chat or `apply-intro-defaults` |
| 7 | vault layout | `init_vault_layout.py` |
| 8 | full setup | `setup.sh` (module venvs) |
| 9 | secrets | Telegram + LLM (+ OpenRouter for knowledge) |
| 10 | smoke | `onboarding_smoke.py --golden-*` |
| 11 | live bot | `run_unified_bot.sh` → `confirm-bot` |
| 12 | finalize | deploy target + `--complete` |

## Common blockers

| Symptom | Fix |
|---------|-----|
| `capabilities.yaml missing` | Run wizard or `apply_capabilities_profile --write` |
| `Set VAULT_PATH` during layout | Set path **before** `init_vault_layout.py` |
| `onboarding_status` import error | Update to latest `main` (fixed `iter_visible_questions` import) |
| `done30 = 0` on dashboards | Rebuild task index — maintainer issue, not onboarding |
| Bot silent | Check `TELEGRAM_UNIFIED_BOT_TOKEN`, process running, VPS vs laptop |

## After bootstrap

- Obsidian plugins: [OBSIDIAN_SETUP.md](OBSIDIAN_SETUP.md)
- Optional connectors: [CONNECTORS.md](CONNECTORS.md)
- VPS deploy: [DEPLOY_VPS.md](DEPLOY_VPS.md)
- Docker is **runtime only** — not a shortcut past this checklist
