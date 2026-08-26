# OSS universality audit (living doc)

Last review: 2026-08-26 (residual F12/F13 debt cleared).

## Done this session (residual debt)

| Item | Origin | Done |
|------|--------|------|
| Dashboard markdown assemble | F13 god-module split | `dashboard/assemble.py` |
| Rsync spine 1–4 | F13 sync carve | `scripts/lib/sync_steps_rsync.sh` |
| Host shims removed | F12 cutover | import `unified_bot.host` only |
| Package shims removed | F13 | `kanban_flow` / `action_log` direct imports |

## Composition

- Host: `unified_bot/host/`
- Boundary: empty allowlist; `shared/memory` may import bots

## Sync layout

- `shared/sync` — plan + lock
- `scripts/lib/sync_steps_rsync.sh` — spine 1–4
- `scripts/lib/sync_steps_charts.sh` / `sync_steps_maintenance.sh`
- Root `obsidian_sync.sh` — bootstrap + orchestration
