"""Unified styling for scheduled Telegram pushes (Rich Message GFM cards)."""
from __future__ import annotations

from shared.i18n import msg


def format_push(title: str, body: str, *, footer: str | None = None) -> str:
    """Life OS card: # title, body, optional italic footer. No ✦ / ASCII rules."""
    title = (title or "").strip().lstrip("#").strip()
    body = (body or "").strip()
    if not body:
        return ""
    parts: list[str] = []
    if title:
        # Titles in messages.yaml may already be plain ("Morning"); normalize to H1.
        parts.append(f"# {title}")
        parts.append("")
    parts.append(body)
    if footer and str(footer).strip():
        parts.extend(["", f"_{str(footer).strip()}_"])
    return "\n".join(parts).strip()


def format_push_sections(
    title: str,
    sections: list[tuple[str, str]],
    *,
    footer: str | None = None,
) -> str:
    """Multi-section brief; empty section bodies dropped. Headings → ##."""
    blocks: list[str] = []
    for heading, text in sections:
        text = (text or "").strip()
        if not text:
            continue
        heading = (heading or "").strip().lstrip("#").strip()
        if heading:
            blocks.append(f"## {heading}\n\n{text}")
        else:
            blocks.append(text)
    if not blocks:
        return ""
    return format_push(title, "\n\n".join(blocks), footer=footer)


async def send_push(
    bot,
    chat_id: int,
    text: str,
    *,
    reply_markup=None,
    disable_notification: bool | None = None,
    disable_web_page_preview: bool | None = True,
) -> None:
    """Send a push card via Rich Messages (fallback: plain long message)."""
    body = (text or "").strip()
    if not body:
        return
    from shared.telegram.messaging import send_long_message

    kwargs = {}
    if reply_markup is not None:
        kwargs["reply_markup"] = reply_markup
    # send_long_message currently takes reply_markup only; notification flags on rich path
    try:
        from shared.telegram.rich_message import rich_messages_enabled, send_rich_message

        if rich_messages_enabled():
            msg_obj = await send_rich_message(
                bot,
                chat_id,
                body,
                reply_markup=reply_markup,
                disable_notification=disable_notification,
            )
            if msg_obj is not None:
                return
    except Exception:
        pass
    await send_long_message(bot, chat_id, body, reply_markup=reply_markup)
