"""Host-level menu detection: domain buttons vs free text."""
from __future__ import annotations

from unified_bot.host import labels as L
from unified_bot.host.constants import (
    DOMAIN_FINANCE,
    DOMAIN_KNOWLEDGE,
    DOMAIN_PLANNING,
    DOMAIN_IDS,
    UI_MODE_AUTO,
)
from unified_bot.host.menu_detection import (
    is_finance_menu_text,
    is_knowledge_menu_text,
    is_planning_menu_text,
)


def mode_from_button(text: str) -> str | None:
    mode = {
        L.mode_finance(): DOMAIN_FINANCE,
        L.mode_planning(): DOMAIN_PLANNING,
        L.mode_knowledge(): DOMAIN_KNOWLEDGE,
        L.mode_auto(): UI_MODE_AUTO,
    }.get(text)
    if not mode or mode == UI_MODE_AUTO:
        return mode
    from shared.capabilities.profile import (
        MODULE_FINANCE,
        MODULE_KNOWLEDGE,
        MODULE_PLANNING,
        get_capabilities,
    )

    prof = get_capabilities()
    module_for_mode = {
        DOMAIN_FINANCE: MODULE_FINANCE,
        DOMAIN_PLANNING: MODULE_PLANNING,
        DOMAIN_KNOWLEDGE: MODULE_KNOWLEDGE,
    }
    mod = module_for_mode.get(mode)
    if mod and not prof.module(mod):
        return None
    return mode


def is_finance_menu(text: str) -> bool:
    return is_finance_menu_text(text)


def is_planning_menu(text: str) -> bool:
    return is_planning_menu_text(text)


def is_knowledge_menu(text: str) -> bool:
    return is_knowledge_menu_text(text)


def is_domain_mode(mode: str) -> bool:
    return mode in DOMAIN_IDS
