#!/usr/bin/env python3
from planning_bot.core.pdmsg import pdmsg
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

pdmsg("auto_05876aac49")
import argparse
import json
import sys
from pathlib import Path

LOG_PREFIX = pdmsg("auto_ee3219e98d")
MONTH_NAMES = ("", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December")

from planning_bot.services.action_log_parser import parse_log_content
from planning_bot.core.config import DONE_COLUMN


def write_log_file(path: Path, events: list, year_month: str) -> None:
    'Operation implementation.'
    if not events:
        return
    y, m = year_month.split("-")
    month_title = f"{MONTH_NAMES[int(m)]} {y}"
    lines = [pdmsg("auto_31eabb5043", _p1=month_title)]
    for e in events:
        ts = e["timestamp"]
        typ = e.get("type", "")
        data = e.get("data") or {}
        data_json = json.dumps(data, ensure_ascii=False, indent=2)
        lines.append(f"## {ts}\n\n")
        lines.append(pdmsg("auto_f68669948a", _p1=typ))
        lines.append(pdmsg("auto_6553160aec"))
        lines.append(data_json)
        lines.append("\n```\n\n---\n\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=pdmsg("auto_11d24a3ae3"))
    ap.add_argument("--vault", type=Path, default=None)
    ap.add_argument("--month", type=str, default=None, help=pdmsg("auto_3bba8862bb"))
    ap.add_argument("--dry-run", action="store_true", help=pdmsg("auto_17bf3030a3"))
    args = ap.parse_args()

    if args.vault:
        logs_dir = Path(args.vault).resolve() / pdmsg("auto_1c7277d3a5") / pdmsg("auto_bcc4709278")
    else:
        from planning_bot.core.config import ACTION_LOGS_DIR
        logs_dir = Path(ACTION_LOGS_DIR)

    if not logs_dir.is_dir():
        print(pdmsg("auto_a9cfe5780b", _p1=logs_dir), flush=True)
        return 1

    if args.month:
        log_files = [logs_dir / f"{LOG_PREFIX}{args.month}.md"]
        log_files = [p for p in log_files if p.exists()]
    else:
        log_files = sorted(logs_dir.glob(f"{LOG_PREFIX}*.md"))

    if not log_files:
        print(pdmsg("auto_eb3c99a9ef"), flush=True)
        return 0

    total_added = 0
    for path in log_files:
        content = path.read_text(encoding="utf-8")
        events = parse_log_content(content)
        if not events:
            continue

        # (comment)
        has_completed = set()
        for e in events:
            if e.get("type") == "task_completed":
                tid = (e.get("data") or {}).get("task_id")
                if tid:
                    has_completed.add(tid)

        # (comment)
        to_append = []
        for e in events:
            if e.get("type") != "task_moved":
                continue
            d = e.get("data") or {}
            if d.get("to") != DONE_COLUMN:
                continue
            tid = d.get("task_id")
            if not tid or tid in has_completed:
                continue
            title = d.get("title") or ""
            category = d.get("category")
            to_append.append({
                "timestamp": e["timestamp"],
                "type": "task_completed",
                "data": {"title": title, "task_id": tid, **({"category": category} if category else {})},
            })
            has_completed.add(tid)

        if not to_append:
            continue

        year_month = path.stem.replace(LOG_PREFIX, "")
        if args.dry_run:
            print(pdmsg("auto_2a09b23885", _p0=path.name, _p2=len(to_append)), flush=True)
            for ev in to_append:
                print(f"  {ev['timestamp']} {ev['data'].get('title', '')[:50]}", flush=True)
            total_added += len(to_append)
            continue

        new_events = events + to_append
        new_events.sort(key=lambda x: (x["timestamp"], (0 if x.get("type") == "task_moved" else 1), x.get("type", "")))

        write_log_file(path, new_events, year_month)
        print(pdmsg("auto_4414441f2a", _p0=path.name, _p2=len(to_append)), flush=True)
        total_added += len(to_append)

    if total_added:
        print(pdmsg("auto_a5e97b8a01", _p1=total_added), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
