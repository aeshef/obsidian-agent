"""User-facing Telegram cards: prefer Rich Messages; HTML/legacy Markdown → GFM."""
from __future__ import annotations

import re
from typing import Any, Optional

from aiogram.types import Message

_TAG_RE = re.compile(r"<[^>]+>")


def html_to_gfm(text: str) -> str:
    s = text or ""
    s = s.replace("<b>", "**").replace("</b>", "**")
    s = s.replace("<strong>", "**").replace("</strong>", "**")
    s = s.replace("<i>", "_").replace("</i>", "_")
    s = s.replace("<em>", "_").replace("</em>", "_")
    s = s.replace("<code>", "`").replace("</code>", "`")
    s = re.sub(r"<pre[^>]*>", "```\n", s, flags=re.I)
    s = re.sub(r"</pre>", "\n```", s, flags=re.I)
    s = re.sub(r"<br\s*/?>", "\n", s, flags=re.I)
    s = _TAG_RE.sub("", s)
    return s.strip()


async def send_card(
    bot,
    chat_id: int,
    text: str,
    *,
    reply_markup: Any = None,
    as_html: bool = False,
) -> None:
    body = html_to_gfm(text) if as_html else (text or "").strip()
    if not body:
        return
    from shared.telegram.messaging import send_long_message

    await send_long_message(bot, chat_id, body, reply_markup=reply_markup)


async def answer_card(
    message: Message,
    text: str,
    *,
    reply_markup: Any = None,
    as_html: bool = False,
    **_ignored: Any,
) -> Optional[Message]:
    body = html_to_gfm(text) if as_html else (text or "").strip()
    if not body:
        return None
    from shared.telegram.rich_message import rich_messages_enabled, send_rich_message

    if rich_messages_enabled():
        msg = await send_rich_message(
            message.bot, message.chat.id, body, reply_markup=reply_markup
        )
        if msg is not None:
            return msg
    return await message.answer(body, reply_markup=reply_markup)


async def edit_card(
    message: Message,
    text: str,
    *,
    reply_markup: Any = None,
    as_html: bool = False,
    **_ignored: Any,
) -> bool:
    """Best-effort edit; Rich Messages cannot always edit — fall back to answer."""
    body = html_to_gfm(text) if as_html else (text or "").strip()
    if not body:
        return False
    try:
        await message.edit_text(body, reply_markup=reply_markup)
        return True
    except Exception:
        await answer_card(message, body, reply_markup=reply_markup)
        return False
