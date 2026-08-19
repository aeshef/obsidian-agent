"""Long-message helpers for Telegram bots."""
from __future__ import annotations

from shared.telegram.flood_guard import send_message_guarded
from shared.telegram.limits import max_message_chars
from shared.telegram.rich_message import rich_max_chars, rich_messages_enabled, send_rich_message
from shared.telegram_utils import split_message, strip_telegram_markdown


async def send_long_message(
    bot,
    chat_id: int,
    text: str,
    reply_markup=None,
    max_len: int | None = None,
    *,
    rich: bool | None = None,
):
    """Send long text; prefer Rich Messages when enabled, else plain chunks.

    Pass rich=False for control panels (lists with #id and [tags] must stay literal).
    """
    body = (text or "").strip()
    if not body:
        return

    use_rich = rich_messages_enabled() if rich is None else bool(rich)
    if use_rich and len(body) <= rich_max_chars():
        msg = await send_rich_message(
            bot, chat_id, body, reply_markup=reply_markup
        )
        if msg is not None:
            return

    plain = strip_telegram_markdown(body)
    limit = max_len if max_len is not None else max_message_chars()
    chunks = split_message(plain, max_len=limit)
    for i, ch in enumerate(chunks):
        await send_message_guarded(
            bot,
            chat_id,
            ch,
            reply_markup=reply_markup if i == len(chunks) - 1 else None,
        )
