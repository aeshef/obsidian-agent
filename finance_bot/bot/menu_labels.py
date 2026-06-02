"""Planning reply-menu labels (same source as planning_bot/app/keyboards.py)."""
from __future__ import annotations
from planning_bot.core.pdmsg import pdmsg
from planning_bot.core.config import CATEGORIES, KANBAN_COLUMNS, PRIORITIES
MAIN_MENU_BUTTONS = frozenset({pdmsg("auto_ca15d9d2aa")})
SUBMENU_BUTTONS = frozenset(
    {
        pdmsg("auto_edc1040220"),
        pdmsg("auto_8771b735cb"),
        pdmsg("auto_a0b7b44b3f"),
        pdmsg("auto_e9917f3011"),
        pdmsg("auto_dc232d1607"),
        pdmsg("auto_322fab4a99"),
        pdmsg("auto_27c8e8e900"),
        pdmsg("auto_f0bc732b56"),
    }
)

def is_planning_menu_button(text: str) -> bool:
    if text in MAIN_MENU_BUTTONS or text in SUBMENU_BUTTONS:
        return True
    if text in KANBAN_COLUMNS:
        return True
    if text.startswith('📋 ') and text[3:] in CATEGORIES:
        return True
    if text.startswith('📋 ') and text[3:] in PRIORITIES:
        return True
    return False