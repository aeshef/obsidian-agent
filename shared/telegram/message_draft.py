"""sendMessageDraft (Bot API 9.3+) without requiring aiogram >= 3.24."""
from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any, Optional

from aiogram.methods.base import TelegramMethod

from shared.telegram.flood_guard import guarded_telegram

if TYPE_CHECKING:
    from aiogram import Bot

log = logging.getLogger("shared.telegram.message_draft")


class SendMessageDraft(TelegramMethod[bool]):
    """https://core.telegram.org/bots/api#sendmessagedraft"""

    __returning__ = bool
    __api_method__ = "sendMessageDraft"

    chat_id: int
    draft_id: int
    text: str
    message_thread_id: Optional[int] = None


def new_draft_id(chat_id: int) -> int:
    """Unique draft_id per stream (non-zero)."""
    base = int(time.time() * 1000) % 2_147_483_647
    return base or ((chat_id % 2_147_483_646) + 1)


async def send_message_draft(
    bot: "Bot",
    *,
    chat_id: int,
    draft_id: int,
    text: str,
) -> bool:
    if not text or not draft_id:
        return False
    payload = text[:4096]
    try:
        result = await guarded_telegram(
            chat_id,
            lambda: bot(
                SendMessageDraft(chat_id=chat_id, draft_id=draft_id, text=payload)
            ),
        )
        return bool(result)
    except Exception as e:
        log.debug("sendMessageDraft failed: %s", e)
        return False
