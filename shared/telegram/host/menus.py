"""Host-level menu detection: domain buttons vs free text."""
from __future__ import annotations

from shared.telegram.host import labels as L
from shared.telegram.host.constants import DOMAIN_IDS
from shared.telegram.host.menu_detection import (
    is_finance_menu_text,
    is_knowledge_menu_text,
    is_planning_menu_text,
)


def mode_from_button(text: str) -> str | None:
    mode = {
        L.mode_finance(): "finance",
        L.mode_planning(): "planning",
        L.mode_knowledge(): "knowledge",
        L.mode_auto(): "auto",
    }.get(text)
    if not mode or mode == "auto":
        return mode
    from shared.capabilities.profile import (
        MODULE_FINANCE,
        MODULE_KNOWLEDGE,
        MODULE_PLANNING,
        get_capabilities,
    )

    prof = get_capabilities()
    module_for_mode = {
        "finance": MODULE_FINANCE,
        "planning": MODULE_PLANNING,
        "knowledge": MODULE_KNOWLEDGE,
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
