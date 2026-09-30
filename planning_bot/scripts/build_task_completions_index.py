#!/usr/bin/env python3
"""Build task_id -> completion timestamp index for dashboard WIP metrics."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from planning_bot.core.config import LOGS_DIR
from planning_bot.services.action_log_parser import collect_events_from_logs, get_completion_events
from shared.vault_paths_config import dashboards_sub, folder


def _output_path(vault: Path) -> Path:
    return vault / folder("dashboards") / dashboards_sub("data") / "task_completions.json"


def build_task_completions_index(*, vault: Path | None = None) -> Path:
    vault = vault or LOGS_DIR.parent
    logs_dir = vault / folder("dashboards") / dashboards_sub("logs")
    out_path = _output_path(vault)
    sources = list(Path(logs_dir).glob("*.md"))
    source_mtime_ms = max((p.stat().st_mtime * 1000 for p in sources), default=0)
    events = collect_events_from_logs(logs_dir)
    completions = get_completion_events(events, filter_batch=True, dedup_per_task=True)

    index: dict[str, str] = {}
    for event in completions:
        data = event.get("data") or {}
        tid = (data.get("task_id") or "").strip().lower()
        if not tid:
            continue
        ts = event.get("timestamp") or event["dt"].strftime("%Y-%m-%d %H:%M:%S")
        prev = index.get(tid)
        if not prev or ts > prev:
            index[tid] = ts

    payload = {
        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "count": len(index),
        "source_mtime_ms": source_mtime_ms,
        "completions": index,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    import tempfile
    import os
    fd, name = tempfile.mkstemp(dir=out_path.parent, prefix=".completions-", suffix=".json")
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(payload, stream, ensure_ascii=False, indent=2)
        Path(name).replace(out_path)
    finally:
        Path(name).unlink(missing_ok=True)
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description="Build task_completions.json for dashboard WIP metrics")
    p.add_argument("--vault", type=Path, default=None)
    args = p.parse_args()
    out = build_task_completions_index(vault=args.vault)
    count = json.loads(out.read_text(encoding="utf-8"))["count"]
    print(f"Wrote {count} completions -> {out}")


if __name__ == "__main__":
    main()
