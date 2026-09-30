from __future__ import annotations
from pathlib import Path
from typing import Any, Dict, Optional
from shared.obsidian_ui.overview import calendar_overview


def render_meeting_focus_dashboard(generated_at: str, analytics: Dict[str, Any], insights_md: str = "", *, week_wiki: Optional[str] = None, life_wiki: Optional[str] = None) -> str:
    return calendar_overview(analytics)


def write_meeting_focus_dashboard(
    path: Path,
    generated_at: str,
    analytics: Dict[str, Any],
    insights_md: str = "",
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    body = render_meeting_focus_dashboard(generated_at, analytics, insights_md)
    from shared.obsidian_ui.layout import present_dashboard
    body = present_dashboard(body, path.parent.parent, "calendar")
    with open(path, "w", encoding="utf-8") as f:
        f.write(body)
