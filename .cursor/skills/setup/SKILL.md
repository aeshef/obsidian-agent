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

1. `source scripts/setup/load_env.sh` (after `cd "$AGENT_ROOT"`)
2. **AskQuestion:** playbook (planning / finance / full) + locale (en / ru)
3. Ask for **VAULT_PATH** (one message, wait for reply) before `init_vault_layout.py`

## Interview CLI

```bash
python3 scripts/onboarding_interview.py next
python3 scripts/onboarding_interview.py answer QUESTION_ID 'user reply'
python3 finance_bot/scripts/apply_initial_accounts.py   # after balances + telegram_id
python3 scripts/onboarding_smoke.py --verify-all --complete --golden-finance
```

## Hard rules

- One secret / one interview question per turn — wait for the user.
- Never dump all tokens at the end.
- Never `cp config/vault_paths.yaml.example` — use `set-locale --refresh-vault-paths`.
- `init_vault_layout.py` only after `capabilities.yaml` exists.
