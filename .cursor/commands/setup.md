# Setup obsidian-agent (guided onboarding)

End-to-end install in **one Cursor chat**: playbook, locale, vault path, personal interview, secrets, opening balances, prompts, smoke.

**Playbook:** `.cursor/skills/obsidian-agent-onboarding/SKILL.md` (section **Single-chat script**).

## Rules

1. **One question per message** for secrets and interview — wait for the user's reply.
2. After each shell command: show **exit code + stderr tail**.
3. Run `python3 scripts/onboarding_interview.py next` to get the next interview question JSON.
4. Save each answer: `python3 scripts/onboarding_interview.py answer ID 'user text'`.
5. Finish with: `python3 scripts/onboarding_smoke.py --verify-all --complete --golden-finance` (or `--golden-planning`).

## Start

**AskQuestion:** playbook (planning / finance / full) + locale (en / ru).

Then follow the skill's **Single-chat script** in order. Do not skip `VAULT_PATH` before `init_vault_layout.py`.
