"""Host-level menu detection: domain buttons vs free text."""
from __future__ import annotations

from bot.config_loader import get_nlu_config, nlu_exact_commands
from bot.reply_menu import is_reply_menu_button
from planning_bot.app.menu_labels import is_planning_menu_button

from shared.telegram.host import labels as L
from shared.telegram.host.constants import DOMAIN_IDS

from knowledge_bot.app.kb_labels import bulk_off, bulk_on, query_button, query_legacy
from knowledge_bot.app.state import BTN_BULK_OFF, BTN_BULK_ON, BTN_QUERY


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
    if is_reply_menu_button(text):
        return True
    cfg = get_nlu_config()
    return text in nlu_exact_commands(cfg)


def is_planning_menu(text: str) -> bool:
    if text in L.mode_button_labels():
        return False
    return is_planning_menu_button(text)


def is_knowledge_menu(text: str) -> bool:
    return text in (BTN_QUERY, BTN_BULK_ON, BTN_BULK_OFF, query_legacy())


def is_domain_mode(mode: str) -> bool:
    return mode in DOMAIN_IDS
