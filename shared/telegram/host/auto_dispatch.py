"""Auto-mode free text/voice dispatch (host router + voice wire)."""
from __future__ import annotations

import asyncio
import logging

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from shared.telegram.host.agent import pick_host_domain
from shared.telegram.host.constants import (
    DOMAIN_FINANCE,
    DOMAIN_GENERAL,
    DOMAIN_KNOWLEDGE,
    DOMAIN_PLANNING,
    DOMAIN_UNIFIED,
    UI_MODE_AUTO,
)
from shared.telegram.host.keyboards import keyboard_for_mode
from shared.telegram.agent_delivery import deliver_agent_answer
from shared.telegram_utils import strip_telegram_markdown

log = logging.getLogger("shared.telegram.host.auto_dispatch")


class MessageWithText:
    """Message proxy with ASR text; voice/audio hidden — no duplicate ASR."""

    __slots__ = ("_message", "text")

    def __init__(self, message: Message, text: str) -> None:
        self._message = message
        self.text = text

    def __getattr__(self, name: str):
        return getattr(self._message, name)

    @property
    def voice(self):
        return None

    @property
    def audio(self):
        return None


async def _dispatch_knowledge(
    message: Message,
    agent_app,
    text: str,
    *,
    state: FSMContext | None = None,
) -> None:
    from knowledge_bot.core.config import load_config
    from knowledge_bot.core.llm import LLMClient
    from knowledge_bot.services.query.text_intent import classify_text_intent
    from shared.telegram.host.knowledge_dispatch import _answer_knowledge_agent

    cfg = load_config()
    llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
    intent = await asyncio.to_thread(
        classify_text_intent, cfg.agent_config_path, llm, text
    )
    log.info("auto dispatch knowledge intent=%s len=%d", intent, len(text))
    wrapped = MessageWithText(message, text)
    if intent == "chat":
        await deliver_agent_answer(
            message.bot,
            message.chat.id,
            agent_app,
            text,
            unified=True,
            reply_markup=keyboard_for_mode(UI_MODE_AUTO, user_id=message.chat.id),
        )
        return
    if intent == "query":
        await _answer_knowledge_agent(wrapped, agent_app, question=text)
        return
    from knowledge_bot.app.handlers.query import handle_message as kb_handle

    await kb_handle(wrapped)


async def dispatch_auto_free_text(
    message: Message,
    state: FSMContext,
    agent_app,
    text: str,
) -> None:
    """Route free text in Auto mode: finance / knowledge / planning / chat."""
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

    if domain == DOMAIN_FINANCE:
        from bot.handlers.financial_query import handle_smart_text

        await handle_smart_text(
            message, state, agent_app=agent_app, text_override=text
        )
        return

    if domain == DOMAIN_KNOWLEDGE:
        await _dispatch_knowledge(message, agent_app, text, state=state)
        return

    if domain == DOMAIN_GENERAL:
        from knowledge_bot.core.config import load_config
        from knowledge_bot.core.llm import LLMClient
        from knowledge_bot.services.query.text_intent import classify_text_intent

        cfg = load_config()
        llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
        intent = await asyncio.to_thread(
            classify_text_intent, cfg.agent_config_path, llm, text
        )
        log.info("auto dispatch general intent=%s", intent)
        if intent == "save":
            from knowledge_bot.app.handlers.query import handle_message as kb_handle

            await kb_handle(MessageWithText(message, text))
            return
        log.info("auto dispatch general → unified (intent=%s)", intent)
        await deliver_agent_answer(
            message.bot,
            message.chat.id,
            agent_app,
            text,
            unified=True,
            reply_markup=keyboard_for_mode(ui_mode, user_id=uid),
        )
        return

    if domain == DOMAIN_PLANNING:
        await deliver_agent_answer(
            message.bot,
            message.chat.id,
            agent_app,
            text,
            domain="planning",
            reply_markup=keyboard_for_mode(ui_mode, user_id=uid),
        )
    elif domain == DOMAIN_UNIFIED:
        log.info("auto dispatch unified (LLM) len=%d", len(text))
        await deliver_agent_answer(
            message.bot,
            message.chat.id,
            agent_app,
            text,
            unified=True,
            reply_markup=keyboard_for_mode(ui_mode, user_id=uid),
        )
    else:
        await deliver_agent_answer(
            message.bot,
            message.chat.id,
            agent_app,
            text,
            unified=True,
            reply_markup=keyboard_for_mode(ui_mode, user_id=uid),
        )
