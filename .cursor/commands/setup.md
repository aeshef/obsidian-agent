# Setup obsidian-agent

**EXECUTE NOW — do not summarize this command or the onboarding skill.**

You are the onboarding operator. `cd` to the directory that contains `unified_bot/` and `scripts/setup.sh` (the obsidian-agent git root). If this workspace is a parent vault, try `Agent`, `obsidian-agent`, `800_Automation/Agent`, then `800_Автоматизация/Agent`.

Follow **every step** in `.cursor/skills/obsidian-agent-onboarding/SKILL.md` section **Single-chat script**. Also load `.cursor/skills/setup/SKILL.md` if needed.

Start immediately:

1. Detect `AGENT_ROOT` and `source scripts/setup/load_env.sh`
2. **AskQuestion:** playbook + locale
3. Ask **VAULT_PATH** (wait for reply) → `python3 scripts/setup/env_tools.py set VAULT_PATH '...'`
4. Continue the single-chat script through interview, secrets, `apply_initial_accounts.py`, and `onboarding_smoke.py --complete`

One question per message. Run shell commands yourself. Show exit codes.
