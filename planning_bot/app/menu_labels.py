"""Planning reply-menu labels (ui_capabilities menu_actions — single source)."""
from __future__ import annotations

from functools import lru_cache

from planning_bot.app.menu_gates import planning_auto_allowed, planning_submenu_allowed
from planning_bot.core.config import CATEGORIES, KANBAN_COLUMNS, PRIORITIES
from planning_bot.core.pdmsg import pdmsg
from shared.capabilities.menu_actions_config import menu_main_keyboard_keys, menu_reply_specs


@lru_cache(maxsize=1)
def all_reply_menu_labels() -> frozenset[str]:
    labels: set[str] = set()
    for spec in menu_reply_specs("planning"):
        key = str(spec.get("label_key") or "").strip()
        if not key or not planning_auto_allowed(key):
            continue
        label = pdmsg(key)
        if label:
            labels.add(label)
    return frozenset(labels)


@lru_cache(maxsize=1)
def main_menu_buttons() -> frozenset[str]:
    labels: set[str] = set()
    for key in menu_main_keyboard_keys("planning"):
        if not planning_auto_allowed(key):
            continue
        label = pdmsg(key)
        if label:
            labels.add(label)
    return frozenset(labels)


@lru_cache(maxsize=1)
def submenu_buttons() -> frozenset[str]:
    """Tasks-filter submenu entries (not on main keyboard)."""
    main = main_menu_buttons()
    return frozenset(label for label in all_reply_menu_labels() if label not in main)


def clear_menu_label_cache() -> None:
    all_reply_menu_labels.cache_clear()
    main_menu_buttons.cache_clear()
    submenu_buttons.cache_clear()


def is_planning_menu_button(text: str) -> bool:
    t = (text or "").strip()
    if not t:
        return False
    if t in all_reply_menu_labels():
        return True
    from planning_bot.services.planning_text_triggers import planning_trigger_phrases

    norm = " ".join(t.casefold().split())
    if norm in planning_trigger_phrases():
        return True
    if t in KANBAN_COLUMNS:
        return planning_submenu_allowed("kanban_column")
    if t.startswith("📋 ") and t[3:] in CATEGORIES:
        return planning_submenu_allowed("category")
    if t.startswith("📋 ") and t[3:] in PRIORITIES:
        return planning_submenu_allowed("priority")
    return False
