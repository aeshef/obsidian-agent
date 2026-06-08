---
name: setup
description: >-
  Run obsidian-agent guided onboarding end-to-end in this chat (/setup).
  Triggers: /setup, setup obsidian-agent, install agent, onboard, first clone.
disable-model-invocation: true
---
# /setup — obsidian-agent onboarding (EXECUTE)

**Do not summarize this skill or the onboarding skill to the user.** You are the operator — run the install now.

## Repo root

```bash
# You must cd here before any command (directory with unified_bot/, scripts/setup.sh)
export AGENT_ROOT="$(pwd)"
```

If the workspace is the parent Obsidian vault, find the agent folder first:

```bash
for d in "800_Автоматизация/Agent" "obsidian-agent" "Agent"; do
  test -f "$d/unified_bot/main.py" && export AGENT_ROOT="$(cd "$d" && pwd)" && break
done
test -n "${AGENT_ROOT:-}" || { echo "Open the obsidian-agent repo root in Cursor, or clone it."; exit 1; }
cd "$AGENT_ROOT"
```

## Playbook

Read and **follow in order** (execute shell steps; do not paraphrase the doc):

`.cursor/skills/obsidian-agent-onboarding/SKILL.md` → section **Single-chat script**

## First action (this message)

1. `cd "$AGENT_ROOT"` && `./scripts/setup.sh` (creates venvs — **required**; system `python3` has no PyYAML)
2. Use **`./scripts/oa-python.sh`** for all Python during onboarding (not bare `python3`)
3. **AskQuestion:** playbook (planning / finance / full) + locale (en / ru)
4. Ask for **VAULT_PATH** before `init_vault_layout.py`

## Interview CLI

```bash
./scripts/oa-python.sh scripts/onboarding_interview.py next
./scripts/oa-python.sh scripts/onboarding_interview.py answer QUESTION_ID 'user reply'
./scripts/oa-python.sh scripts/setup/env_tools.py set DEEPSEEK_API_KEY 'sk-...'
./scripts/oa-python.sh scripts/onboarding_validate_secrets.py --ping-deepseek
./scripts/oa-python.sh finance_bot/scripts/apply_initial_accounts.py
./scripts/run_unified_bot.sh
# user tests Telegram → then:
./scripts/oa-python.sh scripts/onboarding_interview.py confirm-bot
./scripts/oa-python.sh scripts/onboarding_interview.py next   # deploy_target (finalize)
./scripts/oa-python.sh scripts/onboarding_smoke.py --verify-all --complete --ping-deepseek --golden-finance
```

## Start bot

```bash
./scripts/run_unified_bot.sh
```

## Hard rules

- One secret / one interview question per turn — wait for the user.
- **Always ask DeepSeek key** even if `.env` looks set; run `onboarding_validate_secrets.py --ping-deepseek` after paste.
- **Never say “setup complete”** until: `--ping-deepseek` OK + user confirmed bot test (`confirm-bot`) + `finalize` deploy question.
- Never dump all tokens at the end.
- Never `cp config/vault_paths.yaml.example` — use `set-locale --refresh-vault-paths`.
- `init_vault_layout.py` only after `capabilities.yaml` exists.
