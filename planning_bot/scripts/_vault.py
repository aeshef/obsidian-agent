"""Vault path helpers for planning_bot CLI scripts (no Cyrillic in callers)."""
from __future__ import annotations

from pathlib import Path

from shared.vault_paths_config import dashboards_sub, folder, vault_file


def discover_vault(start: Path) -> Path:
    """Walk up from start until vault root markers exist."""
    tasks = folder("tasks")
    dashboards = folder("dashboards")
    for p in [start.resolve(), *start.resolve().parents]:
        if (p / tasks).exists() and (p / dashboards).exists():
            return p
    return start.resolve().parents[3]


def vault_layout(vault: Path) -> dict[str, Path]:
    """Common paths used by chart/maintenance scripts."""
    dash = vault / folder("dashboards")
    data = dash / dashboards_sub("data")
    logs = dash / dashboards_sub("logs")
    charts = dash / dashboards_sub("charts")
    return {
        "vault": vault,
        "tasks": vault / folder("tasks"),
        "goals": vault / folder("goals"),
        "dashboards": dash,
        "data": data,
        "logs": logs,
        "charts": charts,
        "kanban": vault / folder("tasks") / vault_file("kanban_board"),
        "action_log_prefix": logs / vault_file("action_log_prefix"),
    }
