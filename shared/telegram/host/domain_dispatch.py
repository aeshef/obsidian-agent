"""Config-driven domain text dispatch — reply-menu buttons only.

Free text never lands here: the host routes it to the unified agent so pinned
modes keep quick-action keyboards without trapping questions in a domain silo.
"""
from __future__ import annotations

import logging

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from shared.agent.app import AgentApp
from shared.telegram.host.constants import (
    DOMAIN_FINANCE,
    DOMAIN_KNOWLEDGE,
    DOMAIN_PLANNING,
    UI_MODE_AUTO,
)
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


def _menu_matches(domain: str, text: str) -> bool:
    # Resolve detectors at call time so tests can monkeypatch menus.* / domain_dispatch.*.
    key = domain_menu_detection_key(domain) or domain
    detectors = {
        DOMAIN_FINANCE: is_finance_menu,
        DOMAIN_PLANNING: is_planning_menu,
        DOMAIN_KNOWLEDGE: is_knowledge_menu,
    }
    detector = detectors.get(key)
    if detector is None:
        return False
    return detector(text)

def _should_handle_menu(domain: str, ui_mode: str, text: str) -> bool:
    if not _menu_matches(domain, text):
        return False
    if ui_mode == domain:
        return True
    if ui_mode == UI_MODE_AUTO and auto_menu_match_enabled(domain):
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
    """Route reply-menu taps only. True = handled (caller should return)."""
    for domain in domain_routing_order():
        if not agent_app.has_domain(domain):
            continue
        if not _should_handle_menu(domain, ui_mode, text):
            continue
        handler = DOMAIN_HANDLERS.get(domain)
        if handler is None:
            log.warning("domain_dispatch: no handler for %s", domain)
            return False
        log.info("domain_dispatch menu domain=%s ui_mode=%s", domain, ui_mode)
        return await handler(
            message, state, agent_app, text, ui_mode, planning
        )
    return False
