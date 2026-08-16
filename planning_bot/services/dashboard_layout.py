"""Legacy dashboard paths cleanup (standalone files superseded by hub dashboards)."""
from __future__ import annotations

from pathlib import Path

from shared.chart_paths import charts_root
from shared.paths import VaultPaths
from shared.vault_paths_config import folder, vault_file

LEGACY_NUTRITION_DASHBOARD_KEY = "legacy_nutrition_dashboard_md"

# Old Analytics/ paths for agent + insights (moved to Система/). Sync --delete needs local gone.
_LEGACY_CHART_KEYS = (
    "legacy_agent_cost_dashboard_md",
    "legacy_chart_agent_tokens_daily_png",
    "legacy_chart_agent_cost_daily_png",
    "legacy_chart_agent_tools_png",
    "legacy_chart_analytics_insights_md",
)


def _legacy_nutrition_dashboard() -> str:
    try:
        return vault_file(LEGACY_NUTRITION_DASHBOARD_KEY)
    except Exception:
        return ""


def cleanup_legacy_dashboard_files(vault_root: Path | None = None) -> list[str]:
    root = vault_root or VaultPaths().root
    actions: list[str] = []
    dash = root / folder("dashboards")
    legacy_name = _legacy_nutrition_dashboard()
    if legacy_name:
        legacy = dash / legacy_name
        if legacy.is_file():
            try:
                legacy.unlink()
                actions.append(f"deleted legacy {legacy_name}")
            except OSError:
                actions.append(f"failed to delete legacy {legacy_name}")

    charts = charts_root(root)
    for key in _LEGACY_CHART_KEYS:
        try:
            rel = vault_file(key)
        except Exception:
            continue
        path = charts / rel
        if path.is_file():
            try:
                path.unlink()
                actions.append(f"deleted legacy chart {rel}")
            except OSError:
                actions.append(f"failed to delete legacy chart {rel}")
    return actions
