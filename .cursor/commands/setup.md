# Setup obsidian-agent (guided onboarding)

Start **interactive onboarding** for a fresh clone: pick modules, locale, vault layout, prompts, and secrets step by step.

**You must follow** `.cursor/skills/obsidian-agent-onboarding/SKILL.md` as the operator playbook.

## How to run this command

1. Open the **obsidian-agent** repo root in Cursor (folder with `unified_bot/`, `scripts/setup.sh`).
2. Run this command from chat (`/setup`).
3. Use **AskQuestion** for playbook and locale; use **live chat** for secrets (one key at a time — wait for the user to paste each value before continuing).
4. Run shell steps yourself; show exit code + stderr after each step.

## First message to the user

Greet briefly, then **AskQuestion**:

- **Playbook:** Planning-only | Finance-only | Full / custom
- **Locale:** English | Russian

Then proceed phase-by-phase per the skill. **Do not** batch all secret requests at the end.

## Hard gates (do not skip)

1. Write `capabilities.yaml` (`--preset` or `--only-modules` + `--write --patch-env`) **before** `init_vault_layout.py`.
2. `env_tools.py set-locale` + `materialize_locale.py` **before** `init_vault_layout.py`.
3. Never `cp config/vault_paths.yaml.example` — locale examples are applied by `materialize_locale.py`.
4. Copy/scaffold prompts **only for enabled modules** (`ensure_bot_prompts.sh` respects capabilities).
5. After each secret paste → `env_tools.py set KEY 'value'` → confirm with `list-missing` before the next secret.
