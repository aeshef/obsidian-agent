"""Config-driven domain text dispatch (finance / planning / knowledge menus)."""
from __future__ import annotations

import logging
from typing import Optional

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from shared.agent.app import AgentApp
from shared.telegram.host.constants import UI_MODE_AUTO
from shared.telegram.host.domain_handlers import DOMAIN_HANDLERS
from shared.telegram.host.domain_routing import (
    auto_menu_match_enabled,
    domain_menu_detection_key,
    domain_routing_order,
)
from shared.telegram.host.menus import (
    is_finance_menu,
    is_knowledge_menu,
    is_planning_menu,
)

log = logging.getLogger("shared.telegram.host.domain_dispatch")

_MENU_DETECTORS = {
    "finance": is_finance_menu,
    "planning": is_planning_menu,
    "knowledge": is_knowledge_menu,
}


def _menu_matches(domain: str, text: str) -> bool:
    key = domain_menu_detection_key(domain)
    detector = _MENU_DETECTORS.get(key) or _MENU_DETECTORS.get(domain)
    return bool(detector and detector(text))


def _should_handle(domain: str, ui_mode: str, text: str) -> bool:
    if ui_mode == domain:
        return True
    if ui_mode == UI_MODE_AUTO and auto_menu_match_enabled(domain) and _menu_matches(domain, text):
        return True
    return False


async def try_dispatch_domain_text(
    message: Message,
    state: FSMContext,
    agent_app: AgentApp,
    text: str,
    ui_mode: str,
    *,
    planning=None,
) -> bool:
    """Route pinned-domain or reply-menu text. True = handled (caller should return)."""
    for domain in domain_routing_order():
        if not agent_app.has_domain(domain):
            continue
        if not _should_handle(domain, ui_mode, text):
            continue
        handler = DOMAIN_HANDLERS.get(domain)
        if handler is None:
            log.warning("domain_dispatch: no handler for %s", domain)
            return False
        return await handler(
            message, state, agent_app, text, ui_mode, planning
        )
    return False
