#!/usr/bin/env python3
"""Persist daily open-task counts for the interactive dashboard."""

from __future__ import annotations

from planning_bot.core.config import GRAPHICS_DIR
from planning_bot.core.pdmsg import pdmsg
from planning_bot.core.vault_discover import discover_vault
from shared.vault_paths_config import vault_file

import argparse
import json
import os
import sys
import time
from collections import Counter
from datetime import date, datetime
from pathlib import Path
from typing import Any



HISTORY_FILENAME = vault_file("open_tasks_history_json")

def _load_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return []
    snaps = data.get("snapshots")
    if not isinstance(snaps, list):
        return []
    return [s for s in snaps if isinstance(s, dict) and s.get("date")]


def _save_history(path: Path, snapshots: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"snapshots": snapshots}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _wait_for_stable_file(path: Path, stable_seconds: float = 3.0, timeout_seconds: float = 20.0) -> bool:
    """Avoid taking a chart snapshot while Obsidian or the ID watcher is rewriting the board."""
    if not path.exists():
        return False
    started = time.time()
    last_mtime = path.stat().st_mtime
    stable_since = time.time()
    while time.time() - started < timeout_seconds:
        time.sleep(0.5)
        current_mtime = path.stat().st_mtime
        if current_mtime != last_mtime:
            last_mtime = current_mtime
            stable_since = time.time()
            continue
        if time.time() - stable_since >= stable_seconds:
            return True
    return False


def main() -> None:
    p = argparse.ArgumentParser(
        description=pdmsg("auto_c55ab2c2b1"),
    )
    p.add_argument("--vault", type=Path, default=None)
    p.add_argument("--out-dir", type=Path, default=None)
    args = p.parse_args()

    vault = Path(args.vault).resolve() if args.vault else discover_vault(Path(__file__).resolve())
    os.environ["VAULT_PATH"] = str(vault)

    agent_root = Path(__file__).resolve().parent.parent.parent
    if str(agent_root) not in sys.path:
        sys.path.insert(0, str(agent_root))

    from planning_bot.core.config import DONE_COLUMN, KANBAN_COLUMNS, KANBAN_FILE
    from planning_bot.services.kanban import KanbanBoard

    out_dir = Path(args.out_dir).resolve() if args.out_dir else GRAPHICS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    history_path = out_dir / HISTORY_FILENAME

    open_columns = frozenset(KANBAN_COLUMNS[:-1])

    _wait_for_stable_file(KANBAN_FILE)
    board = KanbanBoard()
    tasks = board.get_tasks(exclude_today=False, exclude_blocked=False)

    by_cat: Counter[str] = Counter()
    skipped_no_column = 0
    for t in tasks:
        if t.get("completed"):
            continue
        col = t.get("column")
        if col not in open_columns:
            if col and col not in (DONE_COLUMN, pdmsg("auto_ca7b1482d8")):
                skipped_no_column += 1
            continue
        cat = (t.get("category") or "").strip() or pdmsg("auto_1945da1fe5")
        by_cat[cat] += 1

    total = int(sum(by_cat.values()))
    today_s = date.today().isoformat()
    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")

    snap = {
        "date": today_s,
        "updated_at": now_iso,
        "total": total,
        "by_category": dict(by_cat),
    }

    snapshots = _load_history(history_path)
    # (comment)
    snapshots = [s for s in snapshots if s.get("date") != today_s]
    snapshots.append(snap)
    snapshots.sort(key=lambda s: str(s.get("date", "")))
    _save_history(history_path, snapshots)



if __name__ == "__main__":
    main()
