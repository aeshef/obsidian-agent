#!/usr/bin/env python3
"""CLI wrapper around planning_bot.services.kanban_orphan_heal.

Prefer: python -m planning_bot.services.kanban_orphan_heal
Legacy flags --mode all / --from-json kept for ops.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.setup.load_env import load_repo_env


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--mode", choices=("sync-orphan", "all"), default="sync-orphan")
    ap.add_argument("--since", default="")
    ap.add_argument("--until", default="")
    ap.add_argument("--from-json", default="")
    ap.add_argument("--ids", default="")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    args = ap.parse_args()
    load_repo_env(_ROOT)

    from planning_bot.services import kanban_orphan_heal as heal

    if args.from_json:
        candidates = list(json.loads(Path(args.from_json).read_text(encoding="utf-8")))
        whitelist = {x.strip().lower() for x in args.ids.split(",") if x.strip()} or None
        missing, stats = heal.filter_missing(
            candidates, heal.board_corpus(), id_whitelist=whitelist
        )
        print(
            f"mode=from-json candidates={len(candidates)} missing={len(missing)} "
            f"skip_id={stats['skip_id']} skip_title={stats['skip_title']} skip_filter={stats['skip_filter']}"
        )
        for row in missing[:15]:
            print(f"  {row[3]} {row[4]} {row[0][:70]}")
        if args.dry_run or not missing:
            return 0
        from planning_bot.services.kanban import KanbanBoard

        KanbanBoard().add_tasks_to_backlog(missing)
        print(f"OK restored={len(missing)}")
        return 0

    if args.mode == "all":
        since = None
        if args.since.strip():
            argv = ["--since", args.since, "--days", "36500"]
        else:
            # Explicit bulk: no since filter via a far past date
            argv = ["--since", "2000-01-01"]
        if args.until.strip():
            argv += ["--until", args.until]
        if args.ids.strip():
            argv += ["--ids", args.ids]
        if args.dry_run:
            argv.append("--dry-run")
        return heal.main(argv)

    argv = ["--days", str(args.days)]
    if args.since.strip():
        argv = ["--since", args.since]
    if args.until.strip():
        argv += ["--until", args.until]
    if args.ids.strip():
        argv += ["--ids", args.ids]
    if args.dry_run:
        argv.append("--dry-run")
    return heal.main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
