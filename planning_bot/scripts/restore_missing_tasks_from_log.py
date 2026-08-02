#!/usr/bin/env python3
"""Re-create kanban tasks logged as task_created but missing from board/archive.

Modes:
  sync-orphan (default) — only recent creates that look like sync wipes:
    no task_deleted, not completed, missing from board, created within --since
    (default: 14 days). Never restores intentional deletes.
  all — every missing create without task_deleted/completed (legacy bulk; avoid).

Preserves original task_id and created date.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[2]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from planning_bot.core.config import (
    ACTION_LOG_PREFIX,
    ACTION_LOGS_DIR,
    CATEGORIES,
    KANBAN_ARCHIVE_FILE,
    KANBAN_FILE,
    PRIORITIES,
)
from planning_bot.services.kanban import KanbanBoard
from shared.setup.load_env import load_repo_env

_TS_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", re.MULTILINE)
_ID_RE = re.compile(r"🆔\s*ID:\s*([0-9a-fA-F-]{6,})", re.IGNORECASE)
_TITLE_RE = re.compile(r"^- \[[ xX]\] (.+)$", re.MULTILINE)


def _parse_events(path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    out: list[dict] = []
    for m in _TS_RE.finditer(text):
        ts = m.group(1)
        start = m.end()
        nxt = _TS_RE.search(text, start)
        block = text[start : nxt.start() if nxt else len(text)]
        type_m = re.search(r"\*\*Тип:\*\*\s*(\S+)", block)
        if not type_m:
            type_m = re.search(r"\*\*Type:\*\*\s*(\S+)", block)
        action = (type_m.group(1) if type_m else "").strip()
        jm = re.search(r"```json\n(\{.*?\})\n```", block, re.DOTALL)
        if not jm:
            continue
        try:
            data = json.loads(jm.group(1))
        except json.JSONDecodeError:
            continue
        data["_logged_at"] = ts
        data["_action"] = action
        out.append(data)
    return out


def _parse_when(s: str) -> datetime:
    s = s.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise SystemExit(f"bad datetime: {s}")


def _ids_and_titles(text: str) -> tuple[set[str], set[str]]:
    ids = {m.group(1).lower() for m in _ID_RE.finditer(text or "")}
    titles = {m.group(1).strip().casefold() for m in _TITLE_RE.finditer(text or "")}
    return ids, titles


def _collect_from_logs(
    *,
    since_dt: datetime | None,
    until_dt: datetime | None,
) -> list[dict]:
    created: dict[str, dict] = {}
    completed: set[str] = set()
    deleted: set[str] = set()
    for log_file in sorted(ACTION_LOGS_DIR.glob(f"{ACTION_LOG_PREFIX}*.md")):
        for ev in _parse_events(log_file):
            logged = ev.get("_logged_at", "")
            if logged:
                ev_dt = datetime.strptime(logged, "%Y-%m-%d %H:%M:%S")
                if since_dt and ev_dt < since_dt:
                    continue
                if until_dt and ev_dt > until_dt:
                    continue
            tid = (ev.get("task_id") or "").strip().lower()
            if not tid:
                continue
            action = ev.get("_action") or ""
            if action == "task_created" and ev.get("title"):
                created[tid] = ev
            elif action == "task_completed":
                completed.add(tid)
            elif action == "task_deleted":
                # Explicit intent only — task_removed (monitor) does NOT block restore.
                deleted.add(tid)
    orphans: list[dict] = []
    for tid, ev in created.items():
        if tid in completed or tid in deleted:
            continue
        orphans.append(
            {
                "task_id": tid,
                "title": ev["title"],
                "created": ev.get("_logged_at", ""),
                "category": ev.get("category") or "",
                "priority": ev.get("priority") or "",
            }
        )
    orphans.sort(key=lambda r: r.get("created") or "")
    return orphans


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--mode",
        choices=("sync-orphan", "all"),
        default="sync-orphan",
        help="sync-orphan=recent wipe suspects (default); all=historical bulk",
    )
    ap.add_argument("--since", default="", help="Log timestamp >= YYYY-MM-DD (overrides mode default)")
    ap.add_argument("--until", default="", help="Log timestamp <=")
    ap.add_argument(
        "--from-json",
        default="",
        help="Use precomputed orphan list JSON instead of scanning logs",
    )
    ap.add_argument(
        "--ids",
        default="",
        help="Comma-separated task_ids to restore (whitelist; safest)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    load_repo_env(_ROOT)

    board_text = KANBAN_FILE.read_text(encoding="utf-8") if KANBAN_FILE.exists() else ""
    arch_text = ""
    if KANBAN_ARCHIVE_FILE and KANBAN_ARCHIVE_FILE.exists():
        arch_text = KANBAN_ARCHIVE_FILE.read_text(encoding="utf-8")
    on_ids, on_titles = _ids_and_titles(board_text + "\n" + arch_text)

    id_whitelist = {x.strip().lower() for x in args.ids.split(",") if x.strip()}

    if args.from_json:
        candidates = list(json.loads(Path(args.from_json).read_text(encoding="utf-8")))
    else:
        if args.since:
            since_dt = _parse_when(args.since)
        elif args.mode == "sync-orphan":
            since_dt = datetime.now() - timedelta(days=14)
        else:
            since_dt = None
        until_dt = _parse_when(args.until) if args.until else None
        candidates = _collect_from_logs(since_dt=since_dt, until_dt=until_dt)

    missing: list[tuple[str, ...]] = []
    skipped_present = 0
    skipped_title = 0
    skipped_filter = 0
    for ev in candidates:
        tid = (ev.get("task_id") or "").strip().lower()
        title = (ev.get("title") or "").strip()
        if not tid or not title:
            continue
        if id_whitelist and tid not in id_whitelist:
            skipped_filter += 1
            continue
        if tid in on_ids:
            skipped_present += 1
            continue
        if title.casefold() in on_titles:
            skipped_title += 1
            continue
        cat = ev.get("category") or (CATEGORIES[0] if CATEGORIES else "development")
        pri = ev.get("priority") or (PRIORITIES[0] if PRIORITIES else "medium")
        created = (ev.get("created") or "").strip()
        created_date = created[:10] if len(created) >= 10 else datetime.now().strftime("%Y-%m-%d")
        missing.append((title, cat, pri, tid, created_date))

    print(
        f"mode={args.mode} candidates={len(candidates)} missing={len(missing)} "
        f"skip_id={skipped_present} skip_title={skipped_title} skip_filter={skipped_filter}"
    )
    for row in missing[:15]:
        print(f"  {row[3]} {row[4]} {row[0][:70]}")
    if len(missing) > 15:
        print(f"  ... +{len(missing) - 15} more")

    if args.dry_run or not missing:
        return 0

    board = KanbanBoard()
    board.add_tasks_to_backlog(missing)
    print(f"OK restored={len(missing)} → {KANBAN_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
