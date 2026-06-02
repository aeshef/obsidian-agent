"""Deliver AgentApp answer to Telegram (progress + final message)."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any

from shared.agent.progress import AgentProgress, NullAgentProgress, agent_progress_enabled
from shared.agent.types import AgentAnswer
from shared.telegram.agent_progress import TelegramAgentProgress
from shared.telegram.messaging import send_long_message
from shared.telegram_utils import strip_telegram_markdown

if TYPE_CHECKING:
    from aiogram import Bot

    from shared.agent.app import AgentApp


def _progress_for(bot: "Bot", chat_id: int) -> AgentProgress:
    if not agent_progress_enabled():
        return NullAgentProgress()
    return TelegramAgentProgress(bot, chat_id)


async def deliver_agent_answer(
    bot: "Bot",
    chat_id: int,
    agent_app: "AgentApp",
    question: str,
    *,
    domain: str | None = None,
    unified: bool = False,
    reply_markup: Any = None,
) -> AgentAnswer:
    """Agent loop + optional step status; final — send_long_message (not draft)."""
    progress = _progress_for(bot, chat_id)
    try:
        if unified:
            result = await agent_app.answer_unified(
                chat_id, question, agent_progress=progress
            )
        else:
            if not domain:
                raise ValueError("domain required when unified=False")
            result = await agent_app.answer(
                domain, chat_id, question, agent_progress=progress
            )
    finally:
        await progress.on_complete()

    text = strip_telegram_markdown(result.text)
    if isinstance(progress, TelegramAgentProgress):
        await progress.finalize_answer(text, reply_markup=reply_markup)
    elif not progress.answer_delivered_in_chat():
        await send_long_message(
            bot,
            chat_id,
            text,
            reply_markup=reply_markup,
        )
    if result.media_files:
        from shared.paths import vault_root
        from shared.telegram.kb_media import send_vault_media_files

        await send_vault_media_files(
            bot, chat_id, vault_root(), result.media_files
        )
    return result
