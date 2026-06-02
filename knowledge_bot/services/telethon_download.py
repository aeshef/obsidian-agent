from __future__ import annotations

import asyncio
import logging
import os
from io import BytesIO
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from aiogram.types import Message

_client = None
_client_token: str | None = None
_client_lock = asyncio.Lock()


def telethon_configured() -> bool:
    return bool(
        os.environ.get("TELEGRAM_API_ID", "").strip()
        and os.environ.get("TELEGRAM_API_HASH", "").strip()
    )


async def _get_client(bot_token: str):
    global _client, _client_token
    if not telethon_configured():
        return None
    async with _client_lock:
        if _client is not None and _client.is_connected() and _client_token == bot_token:
            return _client
        if _client is not None and _client.is_connected():
            await _client.disconnect()
        from telethon import TelegramClient
        from telethon.sessions import MemorySession

        api_id = int(os.environ["TELEGRAM_API_ID"].strip())
        api_hash = os.environ["TELEGRAM_API_HASH"].strip()
        _client = TelegramClient(MemorySession(), api_id, api_hash)
        await _client.start(bot_token=bot_token)
        _client_token = bot_token
        return _client


def _bot_token(message: Message) -> str | None:
    bot = getattr(message, "bot", None)
    token = getattr(bot, "token", None) if bot else None
    if token:
        return str(token)
    return (
        os.environ.get("TELEGRAM_UNIFIED_BOT_TOKEN")
        or os.environ.get("TELEGRAM_KNOWLEDGE_BOT_TOKEN")
        or os.environ.get("TELEGRAM_BOT_TOKEN")
        or None
    )


async def download_message_media(message: Message) -> tuple[bytes, str] | None:
    """English docstring omitted (see domain_messages.yaml)."""
    log = logging.getLogger("kb.telethon")
    token = _bot_token(message)
    if not token:
        log.warning("Telethon skip: no bot token")
        return None
    if not telethon_configured():
        log.info("Telethon skip: set TELEGRAM_API_ID + TELEGRAM_API_HASH (my.telegram.org)")
        return None
    try:
        client = await _get_client(token)
        if client is None:
            return None
        chat_id = message.chat.id
        msg_id = message.message_id
        entity = await client.get_entity(chat_id)
        msg = await client.get_messages(entity, ids=msg_id)
        if not msg or not getattr(msg, "media", None):
            log.info("Telethon: no media on msg_id=%s", msg_id)
            return None
        buf = BytesIO()
        await client.download_media(msg, file=buf)
        data = buf.getvalue()
        if not data:
            return None
        name = "telegram_media.bin"
        file_obj = getattr(msg, "file", None)
        if file_obj and getattr(file_obj, "name", None):
            name = file_obj.name
        elif getattr(msg, "video", None) and getattr(msg.video, "file_name", None):
            name = msg.video.file_name
        elif getattr(msg, "document", None) and getattr(msg.document, "file_name", None):
            name = msg.document.file_name
        log.info("Telethon downloaded: msg_id=%s %d bytes name=%s", msg_id, len(data), name)
        return data, name
    except Exception as e:
        log.warning("Telethon download failed msg_id=%s: %s", message.message_id, e)
        return None
