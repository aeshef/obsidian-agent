"""Planning reply-menu labels (same source as planning_bot/app/keyboards.py)."""
from __future__ import annotations

from functools import lru_cache

from planning_bot.app.menu_gates import planning_submenu_allowed
from planning_bot.core.config import CATEGORIES, KANBAN_COLUMNS, PRIORITIES
from planning_bot.core.pdmsg import pdmsg

_SUBMENU_AUTO_KEYS = (
    "auto_edc1040220",
    "auto_8771b735cb",
    "auto_a0b7b44b3f",
    "auto_e9917f3011",
    "auto_dc232d1607",
    "auto_322fab4a99",
    "auto_27c8e8e900",
    "auto_f0bc732b56",
)


@lru_cache(maxsize=1)
def main_menu_buttons() -> frozenset[str]:
    label = pdmsg("auto_ca15d9d2aa")
    return frozenset({label}) if label else frozenset()


@lru_cache(maxsize=1)
def submenu_buttons() -> frozenset[str]:
    labels = {pdmsg(key) for key in _SUBMENU_AUTO_KEYS}
    return frozenset(label for label in labels if label)


def clear_menu_label_cache() -> None:
    main_menu_buttons.cache_clear()
    submenu_buttons.cache_clear()


def is_planning_menu_button(text: str) -> bool:
    if text in main_menu_buttons() or text in submenu_buttons():
        return True
    if text in KANBAN_COLUMNS:
        return planning_submenu_allowed("kanban_column")
    if text.startswith("📋 ") and text[3:] in CATEGORIES:
        return planning_submenu_allowed("category")
    if text.startswith("📋 ") and text[3:] in PRIORITIES:
        return planning_submenu_allowed("priority")
    return False
