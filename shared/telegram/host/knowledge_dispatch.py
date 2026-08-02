"""Knowledge in unified-bot: bulk buttons, queries, media ingest."""
from __future__ import annotations

import logging

from aiogram.types import Message

from shared.agent.app import AgentApp
from shared.telegram.host.constants import DOMAIN_KNOWLEDGE
from shared.telegram.host.keyboards import keyboard_for_mode
from shared.telegram.agent_delivery import deliver_agent_answer

log = logging.getLogger("shared.telegram.host.knowledge")

async def _answer_knowledge_agent(
    message: Message,
    agent_app: AgentApp,
    *,
    question: str | None = None,
) -> None:
    uid = message.from_user.id if message.from_user else message.chat.id
    kb = keyboard_for_mode(DOMAIN_KNOWLEDGE, user_id=uid)
    text = (question or message.text or "").strip()
    await deliver_agent_answer(
        message.bot,
        message.chat.id,
        agent_app,
        text,
        domain=DOMAIN_KNOWLEDGE,
        reply_markup=kb,
    )


async def try_handle_knowledge_text(
    message: Message,
    agent_app: AgentApp,
    state=None,
) -> bool:
    """Handle text in knowledge mode. True = handled."""
    from knowledge_bot.app.menu_dispatch import dispatch_knowledge_menu_button
    from knowledge_bot.app.state import is_bulk_ingest
    from shared.telegram.host.constants import KB_QUERY_PENDING_KEY

    text = (message.text or "").strip()
    if not text:
        return False

    uid = message.from_user.id if message.from_user else 0
    kb = keyboard_for_mode(DOMAIN_KNOWLEDGE, user_id=uid)
    data = await state.get_data() if state is not None else {}

    if await dispatch_knowledge_menu_button(
        message, agent_app, state=state, reply_markup=kb
    ):
        return True

    if is_bulk_ingest(uid):
        from knowledge_bot.app.handlers.query import handle_message as kb_handle

        await kb_handle(message)
        return True

    # Legacy flag clear (button no longer sets a trap).
    if data.get(KB_QUERY_PENDING_KEY) and state is not None:
        await state.update_data(kb_query_pending=False)

    # Menu-only path ends above; free text is handled by host unified dispatch.
    # Keep knowledge-domain agent for any residual callers that land here.
    await deliver_agent_answer(
        message.bot,
        message.chat.id,
        agent_app,
        text,
        unified=True,
        reply_markup=kb,
    )
    return True


async def handle_knowledge_media(message: Message) -> None:
    from knowledge_bot.app.handlers.query import handle_message as kb_handle

    await kb_handle(message)
