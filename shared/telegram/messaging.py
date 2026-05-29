"""Long-message helpers for Telegram bots."""
from __future__ import annotations

from shared.telegram_utils import split_message
from shared.telegram.limits import max_message_chars


async def send_long_message(
    bot, chat_id: int, text: str, reply_markup=None, max_len: int | None = None
):
    """Send long text in chunks (limit from platform.yaml → telegram.max_message_chars)."""
    limit = max_len if max_len is not None else max_message_chars()
    chunks = split_message(text, max_len=limit)
    for i, ch in enumerate(chunks):
        await bot.send_message(
            chat_id=chat_id,
            text=ch,
            reply_markup=reply_markup if i == len(chunks) - 1 else None,
        )
