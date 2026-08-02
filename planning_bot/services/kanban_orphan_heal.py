"""Regular sync-orphan heal for the kanban board.

Same stack as the rest of planning (Python + AGENT_LOCALE / domain_messages).
Restores task_created entries from the last N days that are missing on the board
and were never task_deleted / task_completed.

task_removed (monitor observation) does NOT block heal — that signal is ambiguous
with sync wipes. Intentional deletes must use apply_kanban delete → task_deleted.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Iterable

from planning_bot.core.config import (
    ACTION_LOG_PREFIX,
    ACTION_LOGS_DIR,
    CATEGORIES,
    KANBAN_ARCHIVE_FILE,
    KANBAN_FILE,
    PRIORITIES,
)
from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.kanban import KanbanBoard

_TS_RE = re.compile(r"^## (\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})", re.MULTILINE)
_ID_RE = re.compile(r"🆔\s*ID:\s*([0-9a-fA-F-]{6,})", re.IGNORECASE)
_TITLE_RE = re.compile(r"^- \[[ xX]\] (.+)$", re.MULTILINE)

DEFAULT_SYNC_ORPHAN_DAYS = 7


def parse_log_events(path: Path) -> list[dict]:
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


def ids_and_titles(text: str) -> tuple[set[str], set[str]]:
    ids = {m.group(1).lower() for m in _ID_RE.finditer(text or "")}
    titles = {m.group(1).strip().casefold() for m in _TITLE_RE.finditer(text or "")}
    return ids, titles


def collect_created_orphans(
    log_files: Iterable[Path],
    *,
    since_dt: datetime | None,
    until_dt: datetime | None = None,
) -> list[dict]:
    created: dict[str, dict] = {}
    completed: set[str] = set()
    deleted: set[str] = set()
    for log_file in sorted(log_files):
        for ev in parse_log_events(log_file):
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


def board_corpus() -> str:
    board_text = KANBAN_FILE.read_text(encoding="utf-8") if KANBAN_FILE.exists() else ""
    arch_text = ""
    if KANBAN_ARCHIVE_FILE and Path(KANBAN_ARCHIVE_FILE).exists():
        arch_text = Path(KANBAN_ARCHIVE_FILE).read_text(encoding="utf-8")
    return board_text + "\n" + arch_text


def filter_missing(
    candidates: list[dict],
    corpus: str,
    *,
    id_whitelist: set[str] | None = None,
) -> tuple[list[tuple[str, ...]], dict[str, int]]:
    on_ids, on_titles = ids_and_titles(corpus)
    missing: list[tuple[str, ...]] = []
    stats = {"skip_id": 0, "skip_title": 0, "skip_filter": 0}
    for ev in candidates:
        tid = (ev.get("task_id") or "").strip().lower()
        title = (ev.get("title") or "").strip()
        if not tid or not title:
            continue
        if id_whitelist and tid not in id_whitelist:
            stats["skip_filter"] += 1
            continue
        if tid in on_ids:
            stats["skip_id"] += 1
            continue
        if title.casefold() in on_titles:
            stats["skip_title"] += 1
            continue
        cat = ev.get("category") or (CATEGORIES[0] if CATEGORIES else "development")
        pri = ev.get("priority") or (PRIORITIES[0] if PRIORITIES else "medium")
        created = (ev.get("created") or "").strip()
        created_date = created[:10] if len(created) >= 10 else datetime.now().strftime("%Y-%m-%d")
        missing.append((title, cat, pri, tid, created_date))
    return missing, stats


def heal_sync_orphans(
    *,
    days: int = DEFAULT_SYNC_ORPHAN_DAYS,
    dry_run: bool = False,
    since: datetime | None = None,
    until: datetime | None = None,
    id_whitelist: set[str] | None = None,
) -> dict:
    since_dt = since if since is not None else (datetime.now() - timedelta(days=max(1, days)))
    log_files = sorted(ACTION_LOGS_DIR.glob(f"{ACTION_LOG_PREFIX}*.md"))
    candidates = collect_created_orphans(log_files, since_dt=since_dt, until_dt=until)
    missing, stats = filter_missing(candidates, board_corpus(), id_whitelist=id_whitelist)
    result = {
        "mode": "sync-orphan",
        "since": since_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "candidates": len(candidates),
        "missing": len(missing),
        **stats,
        "restored_ids": [row[3] for row in missing],
        "dry_run": dry_run,
    }
    print(
        pdmsg(
            "kanban_orphan_heal_summary",
            default=(
                "kanban_orphan_heal: mode={mode} candidates={candidates} "
                "missing={missing} skip_id={skip_id} skip_title={skip_title}"
            ),
            mode=result["mode"],
            candidates=result["candidates"],
            missing=result["missing"],
            skip_id=stats["skip_id"],
            skip_title=stats["skip_title"],
        ),
        flush=True,
    )
    for row in missing[:15]:
        print(f"  {row[3]} {row[4]} {row[0][:70]}", flush=True)
    if len(missing) > 15:
        print(f"  ... +{len(missing) - 15} more", flush=True)
    if dry_run or not missing:
        return result
    board = KanbanBoard()
    board.add_tasks_to_backlog(missing)
    print(
        pdmsg(
            "kanban_orphan_heal_ok",
            default="kanban_orphan_heal: restored={count} → {path}",
            count=len(missing),
            path=str(KANBAN_FILE),
        ),
        flush=True,
    )
    return result


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--days", type=int, default=DEFAULT_SYNC_ORPHAN_DAYS)
    ap.add_argument("--since", default="", help="YYYY-MM-DD (overrides --days)")
    ap.add_argument("--until", default="")
    ap.add_argument("--ids", default="", help="Comma-separated task_id whitelist")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    since = None
    if args.since.strip():
        raw = args.since.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                since = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        if since is None:
            raise SystemExit(f"bad --since: {args.since}")
    until = None
    if args.until.strip():
        raw = args.until.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                until = datetime.strptime(raw, fmt)
                break
            except ValueError:
                continue
        if until is None:
            raise SystemExit(f"bad --until: {args.until}")

    whitelist = {x.strip().lower() for x in args.ids.split(",") if x.strip()} or None
    heal_sync_orphans(
        days=args.days,
        dry_run=args.dry_run,
        since=since,
        until=until,
        id_whitelist=whitelist,
    )
    return 0


if __name__ == "__main__":
    # Match other planning services: locale/messages via env already loaded by caller.
    raise SystemExit(main())
