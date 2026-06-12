"""Routines section labels from planning_bot/config/routines.yaml + messages."""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from planning_bot.app.ui import pmsg
from planning_bot.core.pdmsg import pdmsg
from planning_bot.core.settings import get_config_path
from shared.yaml_config import load_merged_config

_LEGACY_CONFIG_HEADERS = {
    "morning": "auto_87b10eda1f",
    "day": "auto_3ed8660b4d",
    "evening": "auto_0f1e39b138",
}
_LEGACY_HISTORY_LABELS = {
    "morning": "auto_7336f91797",
    "day": "auto_c9ee65efdc",
    "evening": "auto_3e5b0bed8a",
}


@lru_cache(maxsize=1)
def load_routines_config() -> dict[str, Any]:
    return load_merged_config(str(get_config_path()), "routines")


def _sections_block() -> dict[str, Any]:
    raw = load_routines_config().get("sections")
    return dict(raw) if isinstance(raw, dict) else {}


def section_config_header(section: str) -> str:
    spec = _sections_block().get(section)
    key = spec.get("config_header_key") if isinstance(spec, dict) else None
    if key:
        val = pmsg(str(key))
        if val and not val.startswith("routines_section_"):
            return val
    legacy = _LEGACY_CONFIG_HEADERS.get(section)
    if legacy:
        return pdmsg(legacy)
    return f"## {section}"


def section_history_label(section: str) -> str:
    spec = _sections_block().get(section)
    key = spec.get("history_label_key") if isinstance(spec, dict) else None
    if key:
        val = pmsg(str(key))
        if val and not val.startswith("routines_section_"):
            return val
    legacy = _LEGACY_HISTORY_LABELS.get(section)
    if legacy:
        return pdmsg(legacy)
    return f"**{section}:**"


SECTION_ORDER = ("morning", "day", "evening")
