#!/usr/bin/env python3
"""Build task_id -> completion timestamp index for dashboard WIP metrics."""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

from planning_bot.core.config import ACTION_LOGS_DIR, LOGS_DIR
from planning_bot.services.action_log_parser import collect_events_from_logs, get_completion_events
from shared.vault_paths_config import dashboards_sub, folder


def _output_path(vault: Path) -> Path:
    return vault / folder("dashboards") / dashboards_sub("data") / "task_completions.json"


def build_task_completions_index(*, vault: Path | None = None) -> Path:
    vault = vault or LOGS_DIR.parent.parent
    out_path = _output_path(vault)
    events = collect_events_from_logs(ACTION_LOGS_DIR)
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
        "completions": index,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path


def main() -> None:
    p = argparse.ArgumentParser(description="Build task_completions.json for dashboard WIP metrics")
    p.add_argument("--vault", type=Path, default=None)
    args = p.parse_args()
    out = build_task_completions_index(vault=args.vault)
    count = json.loads(out.read_text(encoding="utf-8"))["count"]
    print(f"Wrote {count} completions -> {out}")


if __name__ == "__main__":
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    main()
