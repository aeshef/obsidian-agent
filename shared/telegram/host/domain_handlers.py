"""Pinned-domain dispatch handlers (registered by domain id)."""
from __future__ import annotations

import logging
from typing import Optional

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from shared.agent.app import AgentApp
from shared.i18n import msgf
from shared.telegram.host.constants import (
    DOMAIN_FINANCE,
    DOMAIN_KNOWLEDGE,
    DOMAIN_PLANNING,
)
from shared.telegram.host.dispatch import switch_mode
from shared.telegram.host import labels as L
from shared.telegram.host.keyboards import keyboard_for_mode
from shared.telegram.host.menus import is_finance_menu

log = logging.getLogger("shared.telegram.host.domain_handlers")


async def dispatch_finance(
    message: Message,
    state: FSMContext,
    agent_app: AgentApp,
    text: str,
    ui_mode: str,
    planning: Optional[object],
) -> bool:
    del planning
    if ui_mode != DOMAIN_FINANCE:
        await state.update_data(ui_mode=DOMAIN_FINANCE, fixed_domain=DOMAIN_FINANCE)
    if is_finance_menu(text):
        from bot.reply_menu import dispatch_reply_menu_button

        if await dispatch_reply_menu_button(message, state):
            return True
    from bot.handlers.financial_query import handle_smart_text

    await handle_smart_text(message, state, agent_app=agent_app)
    return True


async def dispatch_planning(
    message: Message,
    state: FSMContext,
    agent_app: AgentApp,
    text: str,
    ui_mode: str,
    planning: Optional[object],
) -> bool:
    uid = message.from_user.id if message.from_user else message.chat.id
    if planning is None:
        await message.answer(
            msgf(
                "host",
                "planning_unavailable",
                finance=L.mode_finance(),
                knowledge=L.mode_knowledge(),
            ),
            reply_markup=keyboard_for_mode(ui_mode, user_id=uid),
        )
        return True
    if ui_mode != DOMAIN_PLANNING:
        await state.update_data(ui_mode=DOMAIN_PLANNING, fixed_domain=DOMAIN_PLANNING)
    from planning_bot.app.handlers import commands as planning_commands

    await planning_commands.process_user_text(
        planning, message, state, text, agent_app=agent_app
    )
    return True


async def dispatch_knowledge(
    message: Message,
    state: FSMContext,
    agent_app: AgentApp,
    text: str,
    ui_mode: str,
    planning: Optional[object],
) -> bool:
    del planning, text
    if ui_mode != DOMAIN_KNOWLEDGE:
        await switch_mode(message, state, DOMAIN_KNOWLEDGE)
    from shared.telegram.host.knowledge_dispatch import try_handle_knowledge_text

    await try_handle_knowledge_text(message, agent_app, state=state)
    return True


DOMAIN_HANDLERS = {
    DOMAIN_FINANCE: dispatch_finance,
    DOMAIN_PLANNING: dispatch_planning,
    DOMAIN_KNOWLEDGE: dispatch_knowledge,
}
