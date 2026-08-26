# Hosting without a Mac

**Mac is optional.** Core product = Telegram `unified_bot` + Obsidian vault + LLM.
LaunchAgents, Shortcuts CLI, and Mac↔VPS rsync are connectors — turn them off.

## Minimal (any OS)

1. Clone the repo on a Linux VPS **or** your Windows/Linux desktop (WSL2 fine).
2. Set `.env`: `VAULT_PATH`, `TELEGRAM_UNIFIED_BOT_TOKEN`, `LLM_API_KEY` (or `DEEPSEEK_API_KEY`).
3. `./scripts/setup.sh` → onboarding wizard → `./scripts/run_unified_bot.sh`.
4. Keep the vault in sync yourself: **Obsidian Sync**, Syncthing, Dropbox, git — whatever you already use.

No `SERVER`, no LaunchAgent, no Apple Health required.

## VPS bot + laptop vault (no Mac sync script)

```
Phone/Telegram → unified_bot on VPS (systemd)
Laptop Obsidian ←→ same vault via Obsidian Sync / Syncthing
```

Install the reboot helper on the VPS:

```bash
# on the server, from the deployed bots tree
bash scripts/install_server_reboot_crontab.sh
```

Or use the sample systemd unit: [`../../deploy/systemd/obsidian-agent.service.example`](../../deploy/systemd/obsidian-agent.service.example).

Leave Mac connectors off in `capabilities.yaml`:

```yaml
connectors:
  apple_health: false       # or health_snapshots: false
  apple_calendar: false
  mac_context: false
  gmail_health_pipeline: false
```

## Linux desktop “sync” without LaunchAgent

If you still want periodic maintenance (charts, health parse) on a Linux box that
holds the vault:

```bash
# crontab -e  (example every 15 minutes)
*/15 * * * * cd /path/to/obsidian-agent && ./scripts/obsidian_sync.sh >>/tmp/oa-sync.log 2>&1
```

Many Mac-only steps no-op when connectors are off. Prefer Syncthing for file
mirroring; use `obsidian_sync.sh` only for analytics jobs you care about.

## Windows

- Run the bot under **WSL2** (Ubuntu) — same scripts as Linux.
- Native Windows is not a supported LaunchAgent host; use WSL or a VPS for 24/7.

## Health / calendar without Apple

Produce [health snapshot files](health/FORMAT.md) from Android or manually.
Skip Shortcut binaries — see [shortcuts recipes](shortcuts/README.md).
