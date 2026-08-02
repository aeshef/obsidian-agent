"""Telegram Rich Messages (Bot API 10.1+): sendRichMessage / sendRichMessageDraft.

aiogram 3.13 has no native wrappers — same approach as message_draft.py.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Optional

from aiogram.methods.base import TelegramMethod
from aiogram.types import Message

from shared.agent.platform_config import platform_bool, platform_int
from shared.telegram.flood_guard import guarded_telegram

if TYPE_CHECKING:
    from aiogram import Bot

log = logging.getLogger("shared.telegram.rich_message")


class SendRichMessage(TelegramMethod[Message]):
    """https://core.telegram.org/bots/api#sendrichmessage"""

    __returning__ = Message
    __api_method__ = "sendRichMessage"

    chat_id: int
    rich_message: dict[str, Any]
    disable_notification: Optional[bool] = None
    reply_markup: Optional[Any] = None


class SendRichMessageDraft(TelegramMethod[bool]):
    """https://core.telegram.org/bots/api#sendrichmessagedraft"""

    __returning__ = bool
    __api_method__ = "sendRichMessageDraft"

    chat_id: int
    draft_id: int
    rich_message: dict[str, Any]
    message_thread_id: Optional[int] = None


def rich_messages_enabled() -> bool:
    return platform_bool("telegram", "rich_messages", default=True)


def rich_max_chars() -> int:
    """Soft cap for markdown payload (Telegram rich text ~32KB)."""
    return max(1024, platform_int("telegram", "rich_max_chars", default=32000))


def _markdown_payload(text: str) -> dict[str, Any]:
    return {"markdown": (text or "")[: rich_max_chars()]}


async def send_rich_message(
    bot: "Bot",
    chat_id: int,
    text: str,
    *,
    reply_markup: Any = None,
    disable_notification: bool | None = None,
) -> Message | None:
    """Send GFM-style rich markdown. Returns Message or None on failure."""
    body = (text or "").strip()
    if not body:
        return None
    try:
        return await guarded_telegram(
            chat_id,
            lambda: bot(
                SendRichMessage(
                    chat_id=chat_id,
                    rich_message=_markdown_payload(body),
                    reply_markup=reply_markup,
                    disable_notification=disable_notification,
                )
            ),
        )
    except Exception as e:
        log.info("sendRichMessage failed: %s", e)
        return None


async def send_rich_message_draft(
    bot: "Bot",
    *,
    chat_id: int,
    draft_id: int,
    text: str,
) -> bool:
    """Stream partial rich markdown draft (ephemeral preview)."""
    if not text or not draft_id:
        return False
    try:
        result = await guarded_telegram(
            chat_id,
            lambda: bot(
                SendRichMessageDraft(
                    chat_id=chat_id,
                    draft_id=draft_id,
                    rich_message=_markdown_payload(text),
                )
            ),
        )
        return bool(result)
    except Exception as e:
        log.debug("sendRichMessageDraft failed: %s", e)
        return False
