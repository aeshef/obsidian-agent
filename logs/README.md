# Runtime logs (index)

This folder is **not** the primary log root. Live logs are scattered on purpose
(LaunchAgent stdout, vault `.sync/`, bot packages, VPS). Use this map:

| What | Where |
|------|--------|
| Sync debug / fail | `/tmp/obsidian_sync_debug.log` |
| Sync LaunchAgent | `/tmp/obsidian-sync.out`, `/tmp/obsidian-sync.err` |
| Sync health markers | `{VAULT}/.sync/health.log`, `health_report.md`, `last_sync_ok.txt` |
| Mobile vault export | `{VAULT}/.sync/mobile_vault_export.log` (+ `mobile_vault_last_ok/fail.txt`) |
| Finance dashboard (daily) | `/tmp/finance-dashboard-sync.log`, `finance_bot/logs/` |
| Planning charts / add_ids / iphone | `planning_bot/logs/` |
| Knowledge bot | `knowledge_bot/logs/bot.log` |
| VPS bots / cron | `/root/bots/**/logs/` (SSH) |

Rotation: `common_rotate_log` / `common_scrub_ssh_noise` in `scripts/lib/common.sh`
(called from `obsidian_sync.sh`).

Historical file here: `build_finance_dashboard.log` (legacy local runs).
