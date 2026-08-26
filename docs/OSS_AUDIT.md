# OSS universality audit (living doc)

Last review: 2026-08-26 (F12/F13 deep carve).  
North star: one repo, any locale, any module subset, no author identity in git.

## F12 — composition root

| Item | Status |
|------|--------|
| Host package | **`unified_bot/host/`** (moved from `shared/telegram/host`) |
| Compat shims | `shared/telegram/host/*` re-exports for one release |
| Allowlist | **empty** — bot imports removed from `shared/` (domain modules relocated) |
| Boundary test | `tests/test_host_import_boundary.py` |

## F13 — god modules / sync

| Item | Status |
|------|--------|
| Sync plan | `shared/sync` + `run_sync_plan.py` |
| Sync lock | shell uses `shared.sync.lock.lock_age_seconds` |
| Sync step libs | `scripts/lib/sync_steps_charts.sh`, `sync_steps_maintenance.sh` |
| Kanban flow | package `planning_bot/services/kanban_flow/` + shim |
| Action logger | package `planning_bot/services/action_log/` + shim |
| Finance dashboard | helpers in `bot/services/dashboard/{windows,filters,series}.py` |

## Canvas F01–F20

All closed; see prior commit `ccae196` + this deep carve.

## Verification

```bash
./scripts/oa-python.sh -m pytest \
  tests/test_host_import_boundary.py \
  tests/test_kanban_flow_metrics.py \
  tests/test_sync_plan.py \
  tests/test_telegram_ux_dispatch.py \
  tests/test_agent_sanity.py -q
```
