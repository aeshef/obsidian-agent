"""Reply-menu action specs from config/ui_capabilities.yaml → menu_actions."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

from shared.yaml_config import load_merged_config

_REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"


@lru_cache(maxsize=1)
def _menu_actions_root() -> dict[str, Any]:
    raw = load_merged_config(str(_REPO_CONFIG), "ui_capabilities")
    section = raw.get("menu_actions")
    return section if isinstance(section, dict) else {}


def menu_actions_domain(domain: str) -> dict[str, Any]:
    block = _menu_actions_root().get(domain)
    return block if isinstance(block, dict) else {}


def menu_reply_specs(domain: str) -> list[dict[str, Any]]:
    reply = menu_actions_domain(domain).get("reply")
    if not isinstance(reply, list):
        return []
    return [row for row in reply if isinstance(row, dict)]


def menu_reset_label_keys(domain: str) -> tuple[str, ...]:
    block = menu_actions_domain(domain).get("reset_context")
    if not isinstance(block, dict):
        return ()
    keys = block.get("label_keys")
    if not isinstance(keys, list):
        return ()
    return tuple(str(k).strip() for k in keys if str(k).strip())


def menu_submenu_specs(domain: str) -> list[dict[str, Any]]:
    submenu = menu_actions_domain(domain).get("submenu")
    if not isinstance(submenu, list):
        return []
    return [row for row in submenu if isinstance(row, dict)]


def clear_menu_actions_cache() -> None:
    _menu_actions_root.cache_clear()
