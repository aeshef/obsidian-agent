"""Agent-facing text formatting for kanban flow metrics."""
from __future__ import annotations

from typing import Any


def format_kanban_flow_for_agent(metrics: dict[str, Any], msg: Any) -> str:
    if metrics.get("status") == "no_task_id_events":
        return msg("kanban_flow_agent_no_data")
    s = metrics.get("summary") or {}
    ins = metrics.get("goal_mapping_insight") or {}
    lines = [
        msg("kanban_flow_agent_header", period_end=(metrics.get("period") or {}).get("end", "?")),
        msg(
            "kanban_flow_agent_summary",
            open_tasks=s.get("current_open", 0),
            completions=s.get("total_completions", 0),
            flow_debt=s.get("flow_debt_today", 0),
            lead_p50=s.get("lead_time_p50_days"),
            cycle_p50=s.get("cycle_time_p50_days"),
            blocked_pct=round(100 * float(s.get("blocked_ratio") or 0), 1),
            stale=s.get("stale_open_count", 0),
        ),
        msg(
            "kanban_flow_agent_goal_segment",
            dominant=ins.get("dominant") or "?",
            goal_share=ins.get("goal_mapped_share"),
            daily_share=ins.get("daily_routine_share"),
            unmapped_share=ins.get("unmapped_share"),
        ),
    ]
    cov = metrics.get("coverage") or {}
    lines.append(
        msg(
            "kanban_flow_agent_coverage",
            pct=cov.get("task_id_coverage_pct", 0),
        )
    )
    return "\n".join(lines)
