"""Auto-mode domain handler registry (LLM pick_host_domain → handler)."""
from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Optional

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

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

log = logging.getLogger("shared.telegram.host.auto_dispatch")

AutoHandler = Callable[
    [Message, FSMContext, object, str, str, int],
    Awaitable[None],
]


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


async def _route_knowledge_intent(
    message: Message,
    agent_app,
    text: str,
    *,
    ui_mode: str,
    uid: int,
    auto_unified_kb: bool = True,
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
    log.info("knowledge intent=%s len=%d auto_unified=%s", intent, len(text), auto_unified_kb)
    wrapped = MessageWithText(message, text)
    kb = keyboard_for_mode(ui_mode, user_id=uid)

    if intent == "chat":
        await deliver_agent_answer(
            message.bot,
            message.chat.id,
            agent_app,
            text,
            unified=True,
            reply_markup=kb if auto_unified_kb else keyboard_for_mode(DOMAIN_KNOWLEDGE, user_id=uid),
        )
        return
    if intent == "query":
        await _answer_knowledge_agent(wrapped, agent_app, question=text)
        return
    from knowledge_bot.app.handlers.query import handle_message as kb_handle

    await kb_handle(wrapped)


async def _auto_finance(
    message: Message,
    state: FSMContext,
    agent_app,
    text: str,
    ui_mode: str,
    uid: int,
) -> None:
    from bot.handlers.financial_query import handle_smart_text

    await handle_smart_text(message, state, agent_app=agent_app, text_override=text)


async def _auto_knowledge(
    message: Message,
    state: FSMContext,
    agent_app,
    text: str,
    ui_mode: str,
    uid: int,
) -> None:
    await _route_knowledge_intent(
        message, agent_app, text, ui_mode=UI_MODE_AUTO, uid=uid, auto_unified_kb=True
    )


async def _auto_general(
    message: Message,
    state: FSMContext,
    agent_app,
    text: str,
    ui_mode: str,
    uid: int,
) -> None:
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


async def _auto_planning(
    message: Message,
    state: FSMContext,
    agent_app,
    text: str,
    ui_mode: str,
    uid: int,
) -> None:
    await deliver_agent_answer(
        message.bot,
        message.chat.id,
        agent_app,
        text,
        domain="planning",
        reply_markup=keyboard_for_mode(ui_mode, user_id=uid),
    )


async def _auto_unified(
    message: Message,
    state: FSMContext,
    agent_app,
    text: str,
    ui_mode: str,
    uid: int,
) -> None:
    log.info("auto dispatch unified (LLM) len=%d", len(text))
    await deliver_agent_answer(
        message.bot,
        message.chat.id,
        agent_app,
        text,
        unified=True,
        reply_markup=keyboard_for_mode(ui_mode, user_id=uid),
    )


_AUTO_HANDLERS: dict[str, AutoHandler] = {
    DOMAIN_FINANCE: _auto_finance,
    DOMAIN_KNOWLEDGE: _auto_knowledge,
    DOMAIN_GENERAL: _auto_general,
    DOMAIN_PLANNING: _auto_planning,
    DOMAIN_UNIFIED: _auto_unified,
}


def auto_handler_for(domain: str) -> AutoHandler:
    return _AUTO_HANDLERS.get(domain, _auto_unified)
