"""Auto-mode free text/voice dispatch (host router + voice wire)."""
from __future__ import annotations

import logging

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from shared.telegram.host.agent import pick_host_domain
from shared.telegram.host.auto_routing import MessageWithText, auto_handler_for
from shared.telegram.host.constants import UI_MODE_AUTO

log = logging.getLogger("shared.telegram.host.auto_dispatch")

# Re-export for callers that build ASR proxies.
__all__ = ["MessageWithText", "dispatch_auto_free_text"]


async def dispatch_auto_free_text(
    message: Message,
    state: FSMContext,
    agent_app,
    text: str,
) -> None:
    """Route free text in Auto mode via LLM domain pick → handler registry."""
    data = await state.get_data()
    uid = message.from_user.id if message.from_user else message.chat.id
    ui_mode = data.get("ui_mode", UI_MODE_AUTO)

    domain = await pick_host_domain(
        text,
        ui_mode,
        data.get("fixed_domain"),
        agent_app,
        chat_id=message.chat.id,
    )
    log.info("auto dispatch domain=%s len=%d", domain, len(text))
    handler = auto_handler_for(domain)
    await handler(message, state, agent_app, text, ui_mode, uid)
