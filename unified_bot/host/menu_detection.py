"""Config-driven domain menu detection (config/ui_capabilities.yaml → menu_detection)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from unified_bot.host.constants import DOMAIN_FINANCE, DOMAIN_KNOWLEDGE, DOMAIN_PLANNING
from shared.yaml_config import load_merged_config

_REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"


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
    if _enabled(DOMAIN_FINANCE, "reply_menu", True) and is_reply_menu_button(t):
        return True
    if _enabled(DOMAIN_FINANCE, "nlu_exact", True):
        cfg = get_nlu_config()
        return t in nlu_exact_commands(cfg)
    return False


def is_planning_menu_text(text: str) -> bool:
    from planning_bot.app.menu_labels import is_planning_menu_button
    from unified_bot.host import labels as L

    t = (text or "").strip()
    if not t:
        return False
    if _enabled(DOMAIN_PLANNING, "exclude_host_mode_labels", True) and t in L.mode_button_labels():
        return False
    if not _enabled(DOMAIN_PLANNING, "planning_menu_labels", True):
        return False
    return is_planning_menu_button(t)


def is_knowledge_menu_text(text: str) -> bool:
    from knowledge_bot.app.menu_dispatch import is_knowledge_menu_button

    t = (text or "").strip()
    if not t:
        return False
    if not _enabled(DOMAIN_KNOWLEDGE, "knowledge_buttons", True):
        return False
    return is_knowledge_menu_button(t)
