#!/usr/bin/env python3
"""Kanban flow metrics: daily column snapshots, JSON aggregate, chart suite."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import date, datetime
from pathlib import Path

from planning_bot.core.pdmsg import pdmsg
from planning_bot.core.vault_discover import discover_vault
from planning_bot.services.kanban_flow_charts import (
    chart_aging_buckets,
    chart_arrivals_departures,
    chart_backlog_cemetery,
    chart_cfd,
    chart_deadline_blitz,
    chart_goal_segment_completions,
    chart_lead_cycle_weekly,
    chart_transitions_heatmap,
    chart_wip_goal_segments,
)
from planning_bot.services.kanban_flow import compute_kanban_flow_metrics
from shared.agent.platform_config import platform_int
from shared.chart_paths import chart_path, chart_wikilink_png, charts_root, ensure_parent
from shared.goals.task_segment import ALL_SEGMENTS
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


def _write_chart_note(
    path: Path,
    *,
    title: str,
    subtitle: str,
    png_key: str,
    ready: bool,
    generated_at: str,
) -> None:
    lines = [f"### {title}", "", subtitle, ""]
    if ready:
        lines.append(chart_wikilink_png(png_key))
    else:
        lines.append(f"_{pdmsg('kanban_flow_hub_chart_pending')}_")
    lines.extend(["", f"_{generated_at}_"])
    ensure_parent(path)
    path.write_text("\n".join(lines), encoding="utf-8")


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

    from planning_bot.core.config import KANBAN_COLUMNS, _kanban_schema
    from planning_bot.services.goals_mapper import GoalsMapper
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_index import load_kanban_category_index

    charts_root(vault).mkdir(parents=True, exist_ok=True)
    logs_dir = vault / folder("dashboards")
    action_logs_dir = logs_dir / dashboards_sub("logs")

    col_hist_path = chart_path(vault, "kanban_columns_history_json")
    metrics_json_path = chart_path(vault, "kanban_flow_metrics_json")
    open_hist_path = chart_path(vault, "open_tasks_history_json")

    png_arrivals = chart_path(vault, "chart_kanban_flow_arrivals_png")
    png_cfd = chart_path(vault, "chart_kanban_flow_cfd_png")
    png_lead = chart_path(vault, "chart_kanban_flow_lead_cycle_png")
    png_aging = chart_path(vault, "chart_kanban_flow_aging_png")
    png_trans = chart_path(vault, "chart_kanban_flow_transitions_png")
    png_goal = chart_path(vault, "chart_kanban_flow_goal_mapping_png")
    png_wip_seg = chart_path(vault, "chart_kanban_flow_wip_segments_png")
    png_cemetery = chart_path(vault, "chart_kanban_backlog_cemetery_png")
    png_blitz = chart_path(vault, "chart_kanban_deadline_blitz_png")
    md_arrivals = chart_path(vault, "chart_kanban_flow_arrivals_md")
    md_cfd = chart_path(vault, "chart_kanban_flow_cfd_md")
    md_lead = chart_path(vault, "chart_kanban_flow_lead_cycle_md")
    md_aging = chart_path(vault, "chart_kanban_flow_aging_md")
    md_trans = chart_path(vault, "chart_kanban_flow_transitions_md")
    md_goal = chart_path(vault, "chart_kanban_flow_goal_mapping_md")
    md_wip = chart_path(vault, "chart_kanban_flow_wip_segments_md")
    md_cemetery = chart_path(vault, "chart_kanban_backlog_cemetery_md")
    md_blitz = chart_path(vault, "chart_kanban_deadline_blitz_md")

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

    seg_labels = {seg: pdmsg(f"kanban_flow_segment_{seg}") for seg in ALL_SEGMENTS}
    cfg_window = metrics.get("goal_mapping_insight", {}).get("window_days", 7)
    built: list[str] = []
    drop_partial_week = platform_int(
        "planning_kanban_flow", "drop_partial_week_in_lead_cycle_chart", default=1
    ) == 1
    drop_today_columns = platform_int(
        "planning_kanban_flow", "drop_today_in_column_charts", default=1
    ) == 1

    weekly_series = list(metrics.get("weekly_lead_cycle") or [])
    if drop_partial_week and weekly_series:
        today_iso = date.today().isocalendar()
        this_week = f"{today_iso.year}-W{today_iso.week:02d}"
        weekly_series = [r for r in weekly_series if str(r.get("week")) != this_week]

    column_history_for_charts = list(column_history)
    if drop_today_columns and column_history_for_charts:
        today_s = date.today().isoformat()
        column_history_for_charts = [
            r for r in column_history_for_charts if str(r.get("date")) != today_s
        ]

    if chart_arrivals_departures(
        metrics.get("daily_flow") or [],
        png_arrivals,
        title=pdmsg("kanban_flow_chart_arrivals_title"),
        label_arrivals=pdmsg("kanban_flow_label_arrivals"),
        label_departures=pdmsg("kanban_flow_label_departures"),
        label_debt=pdmsg("kanban_flow_label_flow_debt"),
        label_x=pdmsg("kanban_flow_label_date"),
        rolling_label=pdmsg("kanban_flow_label_rolling_departures", days=cfg_window),
        window=cfg_window,
    ):
        built.append(png_arrivals.name)

    cfd_cols = [c for c in KANBAN_COLUMNS[:-1] if c]
    if chart_cfd(
        column_history_for_charts,
        cfd_cols,
        png_cfd,
        title=pdmsg("kanban_flow_chart_cfd_title"),
        label_x=pdmsg("kanban_flow_label_date"),
        label_y=pdmsg("kanban_flow_label_tasks_in_column"),
    ):
        built.append(png_cfd.name)

    if chart_lead_cycle_weekly(
        weekly_series,
        png_lead,
        title=pdmsg("kanban_flow_chart_lead_cycle_title"),
        label_lead=pdmsg("kanban_flow_label_lead_p50"),
        label_cycle=pdmsg("kanban_flow_label_cycle_p50"),
        label_x=pdmsg("kanban_flow_label_week"),
    ):
        built.append(png_lead.name)

    aging_buckets = (metrics.get("aging") or {}).get("buckets") or {}
    if chart_aging_buckets(
        aging_buckets,
        png_aging,
        title=pdmsg("kanban_flow_chart_aging_title"),
        labels={
            "0_7": pdmsg("kanban_flow_aging_0_7"),
            "8_14": pdmsg("kanban_flow_aging_8_14"),
            "15_30": pdmsg("kanban_flow_aging_15_30"),
            "31_plus": pdmsg("kanban_flow_aging_31_plus"),
            "y_open": pdmsg("kanban_flow_label_open_tasks"),
        },
    ):
        built.append(png_aging.name)

    if chart_transitions_heatmap(
        metrics.get("transitions") or {},
        png_trans,
        title=pdmsg("kanban_flow_chart_transitions_title"),
    ):
        built.append(png_trans.name)

    if chart_goal_segment_completions(
        metrics.get("completions_by_goal_segment") or [],
        png_goal,
        title=pdmsg("kanban_flow_chart_goal_mapping_title"),
        segment_labels=seg_labels,
        label_x=pdmsg("kanban_flow_label_date"),
        label_y=pdmsg("kanban_flow_label_completions"),
        ratio_label=pdmsg("kanban_flow_chart_goal_ratio_label"),
    ):
        built.append(png_goal.name)

    if chart_wip_goal_segments(
        column_history_for_charts,
        png_wip_seg,
        title=pdmsg("kanban_flow_chart_wip_segments_title"),
        segment_labels=seg_labels,
        label_x=pdmsg("kanban_flow_label_date"),
        label_y=pdmsg("kanban_flow_label_open_tasks"),
    ):
        built.append(png_wip_seg.name)

    aging_by_cat = (metrics.get("aging") or {}).get("by_category") or {}
    if chart_backlog_cemetery(
        aging_by_cat,
        png_cemetery,
        title=pdmsg("kanban_flow_chart_cemetery_title"),
        bucket_labels={
            "0_7": pdmsg("kanban_flow_aging_0_7"),
            "8_14": pdmsg("kanban_flow_aging_8_14"),
            "15_30": pdmsg("kanban_flow_aging_15_30"),
            "31_plus": pdmsg("kanban_flow_aging_31_plus"),
        },
    ):
        built.append(png_cemetery.name)

    blitz_counts = ((metrics.get("deadline_blitz") or {}).get("counts") or {})
    if chart_deadline_blitz(
        blitz_counts,
        png_blitz,
        title=pdmsg("kanban_flow_chart_deadline_blitz_title"),
        labels={
            "early": pdmsg("kanban_flow_deadline_early"),
            "on_day": pdmsg("kanban_flow_deadline_on_day"),
            "late": pdmsg("kanban_flow_deadline_late"),
            "no_deadline": pdmsg("kanban_flow_deadline_none"),
            "with_dl": pdmsg("kanban_flow_deadline_panel_timed"),
            "y": pdmsg("kanban_flow_label_completions"),
            "panel_timed": pdmsg("kanban_flow_deadline_panel_timed"),
            "panel_none": pdmsg("kanban_flow_deadline_panel_none"),
        },
    ):
        built.append(png_blitz.name)

    now_iso = datetime.now().strftime("%Y-%m-%d %H:%M")
    _write_chart_note(
        md_arrivals,
        title=pdmsg("kanban_flow_chart_arrivals_title"),
        subtitle=pdmsg("kanban_flow_hub_section_arrivals"),
        png_key="chart_kanban_flow_arrivals_png",
        ready=png_arrivals.name in built,
        generated_at=now_iso,
    )
    _write_chart_note(
        md_cfd,
        title=pdmsg("kanban_flow_chart_cfd_title"),
        subtitle=pdmsg("kanban_flow_hub_section_cfd"),
        png_key="chart_kanban_flow_cfd_png",
        ready=png_cfd.name in built,
        generated_at=now_iso,
    )
    _write_chart_note(
        md_lead,
        title=pdmsg("kanban_flow_chart_lead_cycle_title"),
        subtitle=pdmsg("kanban_flow_hub_section_lead"),
        png_key="chart_kanban_flow_lead_cycle_png",
        ready=png_lead.name in built,
        generated_at=now_iso,
    )
    _write_chart_note(
        md_aging,
        title=pdmsg("kanban_flow_chart_aging_title"),
        subtitle=pdmsg("kanban_flow_hub_section_aging"),
        png_key="chart_kanban_flow_aging_png",
        ready=png_aging.name in built,
        generated_at=now_iso,
    )
    _write_chart_note(
        md_trans,
        title=pdmsg("kanban_flow_chart_transitions_title"),
        subtitle=pdmsg("kanban_flow_hub_section_transitions"),
        png_key="chart_kanban_flow_transitions_png",
        ready=png_trans.name in built,
        generated_at=now_iso,
    )
    _write_chart_note(
        md_goal,
        title=pdmsg("kanban_flow_chart_goal_mapping_title"),
        subtitle=pdmsg("kanban_flow_hub_section_goal_mapping"),
        png_key="chart_kanban_flow_goal_mapping_png",
        ready=png_goal.name in built,
        generated_at=now_iso,
    )
    _write_chart_note(
        md_wip,
        title=pdmsg("kanban_flow_chart_wip_segments_title"),
        subtitle=pdmsg("kanban_flow_hub_section_wip_segments"),
        png_key="chart_kanban_flow_wip_segments_png",
        ready=png_wip_seg.name in built,
        generated_at=now_iso,
    )
    _write_chart_note(
        md_cemetery,
        title=pdmsg("kanban_flow_chart_cemetery_title"),
        subtitle=pdmsg("kanban_flow_hub_section_cemetery"),
        png_key="chart_kanban_backlog_cemetery_png",
        ready=png_cemetery.name in built,
        generated_at=now_iso,
    )
    _write_chart_note(
        md_blitz,
        title=pdmsg("kanban_flow_chart_deadline_blitz_title"),
        subtitle=pdmsg("kanban_flow_hub_section_deadline_blitz"),
        png_key="chart_kanban_deadline_blitz_png",
        ready=png_blitz.name in built,
        generated_at=now_iso,
    )
    print(pdmsg("kanban_flow_build_ok", charts=len(built), hub="-", json=str(metrics_json_path)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
