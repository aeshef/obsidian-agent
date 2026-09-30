"""Small, safe Markdown subset shared by Telegram send and edit paths.

Explicit HTML/entities belong to their caller. Plain user values must be escaped
at template boundaries; this renderer never interprets raw HTML as markup.
"""
from __future__ import annotations

import re
from html import escape


def telegram_html(text: str) -> str:
    protected: list[str] = []

    def stash(value: str) -> str:
        protected.append(value)
        return f"\x00{len(protected) - 1}\x00"

    # Do not let input forge placeholders used for protected code/links.
    text = text.replace("\x00", "")
    text = re.sub(r"```[^\n`]*\n([\s\S]*?)```", lambda m: stash("<pre>" + escape(m[1]) + "</pre>"), text)
    text = re.sub(r"`([^`\n]+)`", lambda m: stash("<code>" + escape(m[1]) + "</code>"), text)
    text = re.sub(r"\[([^]\n]+)\]\((https?://[^\s)]+)\)",
                  lambda m: stash('<a href="' + escape(m[2], quote=True) + '">' + escape(m[1]) + '</a>'), text)
    text = escape(text)
    text = re.sub(r"(?m)^#{1,6} +(.+)$", r"<b>\1</b>", text)
    text = re.sub(r"\*\*([^*\n]+)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"__([^_\n]+)__", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\w)_([^_\n]+)_(?!\w)", r"<i>\1</i>", text)
    text = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<i>\1</i>", text)
    text = re.sub(r"(?m)^[-*] +", "• ", text)
    return re.sub(r"\x00(\d+)\x00", lambda m: protected[int(m[1])], text)


async def presentation_middleware(make_request, bot, method):
    """Cover direct message.answer/edit_text as well as shared send helpers.

    Never touch explicit entities, HTML/MarkdownV2, captions, or API control text.
    """
    original = method
    if getattr(method, "__api_method__", "") in {"sendMessage", "editMessageText"}:
        mode = getattr(method, "parse_mode", None)
        from aiogram.client.default import Default
        inherited = isinstance(mode, Default)
        effective = bot.default.parse_mode if inherited else mode
        if effective is None and not getattr(method, "entities", None):
            method = method.model_copy(update={"text": telegram_html(method.text), "parse_mode": "HTML"})
    try:
        return await make_request(bot, method)
    except Exception as exc:
        from aiogram.exceptions import TelegramBadRequest
        if method is original or not isinstance(exc, TelegramBadRequest) or "parse entities" not in str(exc).lower():
            raise
        # Telegram explicitly rejected the markup: retry this unsent message as text.
        from shared.telegram_utils import strip_telegram_markdown
        plain = original.model_copy(update={"text": strip_telegram_markdown(original.text), "parse_mode": None})
        return await make_request(bot, plain)
