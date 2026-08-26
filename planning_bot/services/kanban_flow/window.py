"""Flow chart window settings from platform.yaml (no magic numbers)."""
from __future__ import annotations

from shared.agent.platform_config import platform_int


def flow_window_days(*, default: int = 7) -> int:
    return platform_int("planning_kanban_flow", "rolling_window_days", default=default)


def _flow_cfg() -> dict[str, int]:
    return {
        "rolling_window_days": max(1, flow_window_days()),
        "history_max_days": max(
            30, platform_int("planning_kanban_flow", "history_max_days", default=365)
        ),
        "aging_stale_days": max(
            1, platform_int("planning_kanban_flow", "aging_stale_days", default=14)
        ),
        "lead_time_max_days": max(
            7, platform_int("planning_kanban_flow", "lead_time_max_days", default=180)
        ),
        "replay_min_task_id_coverage_pct": max(
            1,
            min(
                100,
                platform_int(
                    "planning_kanban_flow",
                    "replay_min_task_id_coverage_pct",
                    default=95,
                ),
            ),
        ),
        "replay_min_events_per_month": max(
            20,
            platform_int(
                "planning_kanban_flow", "replay_min_events_per_month", default=200
            ),
        ),
        "trusted_interpolate_max_gap_days": max(
            1,
            platform_int(
                "planning_kanban_flow",
                "trusted_interpolate_max_gap_days",
                default=2,
            ),
        ),
    }
