"""Config-driven domain menu detection (config/ui_capabilities.yaml → menu_detection)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from shared.yaml_config import load_merged_config

_REPO_CONFIG = Path(__file__).resolve().parents[3] / "config"


@lru_cache(maxsize=1)
def _menu_detection() -> dict[str, dict]:
    raw = load_merged_config(str(_REPO_CONFIG), "ui_capabilities")
    section = raw.get("menu_detection")
    if not isinstance(section, dict):
        return {}
    out: dict[str, dict] = {}
    for domain, spec in section.items():
        if isinstance(domain, str) and isinstance(spec, dict):
            out[domain.strip()] = spec
    return out


def clear_menu_detection_cache() -> None:
    _menu_detection.cache_clear()


def _enabled(domain: str, key: str, default: bool = True) -> bool:
    spec = _menu_detection().get(domain) or {}
    val = spec.get(key, default)
    return bool(val) if val is not None else default


def is_finance_menu_text(text: str) -> bool:
    from bot.config_loader import get_nlu_config, nlu_exact_commands
    from bot.reply_menu import is_reply_menu_button

    t = (text or "").strip()
    if not t:
        return False
    if _enabled("finance", "reply_menu", True) and is_reply_menu_button(t):
        return True
    if _enabled("finance", "nlu_exact", True):
        cfg = get_nlu_config()
        return t in nlu_exact_commands(cfg)
    return False


def is_planning_menu_text(text: str) -> bool:
    from planning_bot.app.menu_labels import is_planning_menu_button
    from shared.telegram.host import labels as L

    t = (text or "").strip()
    if not t:
        return False
    if _enabled("planning", "exclude_host_mode_labels", True) and t in L.mode_button_labels():
        return False
    if not _enabled("planning", "planning_menu_labels", True):
        return False
    return is_planning_menu_button(t)


def is_knowledge_menu_text(text: str) -> bool:
    from knowledge_bot.app.kb_labels import bulk_off, bulk_on, query_button, query_legacy
    from knowledge_bot.app.state import BTN_BULK_OFF, BTN_BULK_ON, BTN_QUERY

    t = (text or "").strip()
    if not t:
        return False
    if not _enabled("knowledge", "knowledge_buttons", True):
        return False
    return t in (BTN_QUERY, BTN_BULK_ON, BTN_BULK_OFF, query_legacy())
