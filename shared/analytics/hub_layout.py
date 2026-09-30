"""Analytics hub: evidence summary followed by interactive exploration."""
from pathlib import Path
from typing import Callable
from shared.obsidian_ui.overview import analytics_overview


def render_analytics_hub(vault: Path, *, ts: str, msg: Callable[[str], str]) -> str:
    return analytics_overview(vault)
