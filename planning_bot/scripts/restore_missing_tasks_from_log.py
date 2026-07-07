#!/usr/bin/env python3
"""Re-create kanban tasks logged as task_created but missing from the board."""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from planning_bot.core.config import ACTION_LOGS_DIR, ACTION_LOG_PREFIX, CATEGORIES, KANBAN_FILE, PRIORITIES
from planning_bot.services.kanban import KanbanBoard
from shared.setup.load_env import load_repo_env


def _parse_log(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    out: list[dict] = []
    ts_re = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", re.MULTILINE)
    for m in ts_re.finditer(text):
        ts = m.group(1)
        start = m.end()
        nxt = ts_re.search(text, start)
        block = text[start : nxt.start() if nxt else len(text)]
        if "task_created" not in block:
            continue
        jm = re.search(r"```json\n(\{.*?\})\n```", block, re.DOTALL)
        if not jm:
            continue
        try:
            data = json.loads(jm.group(1))
        except json.JSONDecodeError:
            continue
        if data.get("task_id") and data.get("title"):
            data["_logged_at"] = ts
            out.append(data)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--since", default="", help="Log timestamp >= YYYY-MM-DD or YYYY-MM-DD HH:MM")
    ap.add_argument("--until", default="", help="Log timestamp <= (same formats)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    load_repo_env(_ROOT)

    board = KanbanBoard()
    board.load()
    on_board = board.content

    def _parse_when(s: str) -> datetime:
        s = s.strip()
        for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        raise SystemExit(f"bad datetime: {s}")

    since_dt = _parse_when(args.since) if args.since else None
    until_dt = _parse_when(args.until) if args.until else None

    missing: list[tuple[str, str, str, str]] = []
    for log_file in sorted(ACTION_LOGS_DIR.glob(f"{ACTION_LOG_PREFIX}*.md")):
        for ev in _parse_log(log_file):
            logged = ev.get("_logged_at", "")
            if logged:
                ev_dt = datetime.strptime(logged, "%Y-%m-%d %H:%M:%S")
                if since_dt and ev_dt < since_dt:
                    continue
                if until_dt and ev_dt > until_dt:
                    continue
            tid = ev["task_id"]
            if tid in on_board:
                continue
            title = ev["title"]
            cat = ev.get("category") or (CATEGORIES[0] if CATEGORIES else "development")
            pri = ev.get("priority") or (PRIORITIES[0] if PRIORITIES else "medium")
            missing.append((title, cat, pri, tid))

    if not missing:
        print("no missing task_created entries")
        return 0

    print(f"restore {len(missing)} task(s)")
    for row in missing[:10]:
        print(" ", row[3], row[0][:60])
    if len(missing) > 10:
        print(f"  ... +{len(missing) - 10} more")

    if args.dry_run:
        return 0

    board.add_tasks_to_backlog(missing)
    print(f"OK → {KANBAN_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
