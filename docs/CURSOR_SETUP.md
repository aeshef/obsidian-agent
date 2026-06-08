# Cursor `/setup` not showing?

## Why

Cursor lists slash commands from:

- `{workspaceFolder}/.cursor/commands/*.md`
- `~/.cursor/commands/*.md` (global)
- Skills with explicit invocation: **`@setup`** (`.cursor/skills/setup/SKILL.md`)

If you opened the **parent Obsidian vault** instead of the **obsidian-agent** repo, `/setup` from the agent subfolder is invisible.

Pasting `…/SKILL.md` into chat makes the model **summarize** the doc — it does not run onboarding.

## Fix

### Option A (recommended)

**File → Open Folder** → select the git clone root (`obsidian-agent/`, must contain `unified_bot/`).

Then in chat: **`/setup`** or **`@setup`**.

### Option B — agent inside vault

If the repo is `…/Obsidian Vault/obsidian-agent/` and you keep the vault as workspace:

```bash
mkdir -p "/path/to/Obsidian Vault/.cursor/commands"
cp obsidian-agent/.cursor/commands/setup.md "/path/to/Obsidian Vault/.cursor/commands/"
```

Reload Cursor window. `/setup` appears at vault root.

### Option C — global command

```bash
mkdir -p ~/.cursor/commands
cp /path/to/obsidian-agent/.cursor/commands/setup.md ~/.cursor/commands/obsidian-agent-setup.md
```

Use `/obsidian-agent-setup` in any project (still `cd` to agent root in the script).

## `/setup` not in autocomplete?

Cursor builds differ:

- **Agent chat** (not Ask): type `/` — commands from `.cursor/commands/*.md`
- If no dropdown: type full name `/setup` or `/obsidian-agent-setup` and press Enter (still works via `cursor_commands`)
- **`@setup`** — skill picker (`.cursor/skills/setup/SKILL.md`)
- **Reload:** `Cmd+Shift+P` → Developer: Reload Window

Autocomplete missing is a known Cursor UI quirk; execution via Enter or `@setup` is the reliable path.

## Verify

Workspace = folder with `unified_bot/` and `.cursor/commands/setup.md`.

Run `./scripts/setup.sh` once (PyYAML lives in venv, not system Python).
