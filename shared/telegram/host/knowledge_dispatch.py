"""Knowledge in unified-bot: bulk buttons, queries, media ingest."""
from __future__ import annotations

import asyncio
import logging

from aiogram.types import Message

from shared.agent.app import AgentApp
from shared.i18n import msg
from shared.telegram.host.constants import DOMAIN_KNOWLEDGE, KB_QUERY_PENDING_KEY
from shared.telegram.host.keyboards import keyboard_for_mode, knowledge_keyboard
from shared.telegram.host.menus import is_knowledge_menu
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
    from knowledge_bot.app.state import BTN_BULK_OFF, BTN_BULK_ON, is_bulk_ingest

    text = (message.text or "").strip()
    if not text:
        return False

    uid = message.from_user.id if message.from_user else 0
    kb = keyboard_for_mode(DOMAIN_KNOWLEDGE, user_id=uid)
    data = await state.get_data() if state is not None else {}

    if text == BTN_BULK_ON:
        from knowledge_bot.app.handlers.modes import enable_bulk_ingest

        await enable_bulk_ingest(message, reply_markup=knowledge_keyboard(bulk_active=True), state=state)
        return True

    if text == BTN_BULK_OFF:
        from knowledge_bot.app.handlers.modes import disable_bulk_ingest

        await disable_bulk_ingest(message, reply_markup=knowledge_keyboard(bulk_active=False), state=state)
        return True

    if is_knowledge_menu(text):
        if state is not None:
            await state.update_data(kb_query_pending=True)
        await message.answer(msg("knowledge", "query_prompt"), reply_markup=kb)
        return True

    if is_bulk_ingest(uid):
        from knowledge_bot.app.handlers.query import handle_message as kb_handle

        await kb_handle(message)
        return True

    # Explicit query after the query-base button
    if data.get(KB_QUERY_PENDING_KEY):
        if state is not None:
            await state.update_data(kb_query_pending=False)
        await _answer_knowledge_agent(message, agent_app, question=text)
        return True

    # Normal mode: LLM decides — new note (review) or knowledge query
    from knowledge_bot.core.config import load_config
    from knowledge_bot.core.llm import LLMClient
    from knowledge_bot.services.query.text_intent import classify_text_intent

    cfg = load_config()
    llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
    intent = await asyncio.to_thread(
        classify_text_intent, cfg.agent_config_path, llm, text
    )
    log.info("knowledge text intent: %s len=%d", intent, len(text))

    if intent == "chat":
        await deliver_agent_answer(
            message.bot,
            message.chat.id,
            agent_app,
            text,
            unified=True,
            reply_markup=kb,
        )
        return True

    if intent == "query":
        await _answer_knowledge_agent(message, agent_app, question=text)
        return True

    from knowledge_bot.app.handlers.query import handle_message as kb_handle

    await kb_handle(message)
    return True


async def handle_knowledge_media(message: Message) -> None:
    from knowledge_bot.app.handlers.query import handle_message as kb_handle

    await kb_handle(message)
