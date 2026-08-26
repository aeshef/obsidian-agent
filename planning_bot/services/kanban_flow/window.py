"""Flow chart window settings from platform.yaml (no magic numbers)."""
from __future__ import annotations

from shared.agent.platform_config import platform_int


def flow_window_days(*, default: int = 7) -> int:
    return platform_int("planning_kanban_flow", "rolling_window_days", default=default)
