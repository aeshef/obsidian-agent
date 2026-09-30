#!/usr/bin/env python3
"""Kanban flow metrics: daily column snapshots and interactive dashboard data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path

from planning_bot.core.pdmsg import pdmsg
from planning_bot.core.vault_discover import discover_vault
from planning_bot.services.kanban_flow import compute_kanban_flow_metrics
from shared.chart_paths import chart_path, charts_root, ensure_parent
from shared.vault_paths_config import dashboards_sub, folder


def _load_trusted_open_totals(path: Path) -> dict[str, int]:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    snaps = raw.get("snapshots") if isinstance(raw, dict) else None
    if not isinstance(snaps, list):
        return {}
    out: dict[str, int] = {}
    for s in snaps:
        d = str((s or {}).get("date", ""))
        if not d:
            continue
        try:
            out[d] = int((s or {}).get("total", 0) or 0)
        except (TypeError, ValueError):
            continue
    return out


def _goals_mapping_fingerprint(mapping_path: Path) -> str:
    if not mapping_path.is_file():
        return ""
    return hashlib.sha256(mapping_path.read_bytes()).hexdigest()


def _goals_mapping_changed(vault: Path, mapping_path: Path) -> bool:
    """True when goals_task_mapping.json changed since last column-history backfill."""
    marker = vault / ".sync" / "kanban_flow_goals_mapping_fingerprint.txt"
    if not marker.is_file():
        return False
    cur = _goals_mapping_fingerprint(mapping_path)
    prev = marker.read_text(encoding="utf-8").strip()
    return bool(cur) and cur != prev


def _persist_goals_mapping_fingerprint(vault: Path, mapping_path: Path) -> None:
    cur = _goals_mapping_fingerprint(mapping_path)
    if not cur:
        return
    marker = vault / ".sync" / "kanban_flow_goals_mapping_fingerprint.txt"
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(cur + "\n", encoding="utf-8")


def main() -> int:
    p = argparse.ArgumentParser(description=pdmsg("kanban_flow_build_desc"))
    p.add_argument("--vault", type=Path, default=None)
    p.add_argument(
        "--backfill-columns",
        action="store_true",
        help="Force replay column snapshots from full action-log history",
    )
    p.add_argument(
        "--no-backfill",
        action="store_true",
        help="Skip auto backfill even when column history is sparse",
    )
    args = p.parse_args()

    vault = Path(args.vault).resolve() if args.vault else discover_vault(Path(__file__).resolve())
    os.environ["VAULT_PATH"] = str(vault)

    agent_root = Path(__file__).resolve().parent.parent.parent
    if str(agent_root) not in sys.path:
        sys.path.insert(0, str(agent_root))

    from planning_bot.core.config import _kanban_schema
    from planning_bot.services.goals_mapper import GoalsMapper
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_index import load_kanban_category_index

    charts_root(vault).mkdir(parents=True, exist_ok=True)
    logs_dir = vault / folder("dashboards")
    action_logs_dir = logs_dir / dashboards_sub("logs")

    col_hist_path = chart_path(vault, "kanban_columns_history_json")
    metrics_json_path = chart_path(vault, "kanban_flow_metrics_json")
    open_hist_path = chart_path(vault, "open_tasks_history_json")

    board = KanbanBoard()
    tasks = board.get_tasks(exclude_today=False, exclude_blocked=False)
    cat_by_id, cat_by_title = load_kanban_category_index(vault)

    mapper = GoalsMapper()
    schema = _kanban_schema()
    trusted_open_totals = _load_trusted_open_totals(open_hist_path)

    backfill_columns = args.backfill_columns
    if not backfill_columns and _goals_mapping_changed(vault, mapper.mapping_file):
        backfill_columns = True

    metrics, column_history = compute_kanban_flow_metrics(
        vault,
        action_logs_dir=action_logs_dir,
        column_history_path=col_hist_path,
        kanban_schema=schema,
        mapping=mapper.mapping,
        board_tasks=tasks,
        cat_by_id=cat_by_id,
        cat_by_title=cat_by_title,
        backfill_columns=backfill_columns,
        allow_auto_backfill=not args.no_backfill,
        trusted_open_totals=trusted_open_totals,
    )

    col_meta = (metrics.get("column_history_meta") or {})
    if backfill_columns or col_meta.get("mode") == "backfill":
        _persist_goals_mapping_fingerprint(vault, mapper.mapping_file)

    ensure_parent(metrics_json_path)
    metrics_json_path.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    from unified_bot.integrations.dashboard_datasets import refresh_progress
    refresh_progress(vault)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
