"""Send media from vault (knowledge note attachments)."""
from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile

log = logging.getLogger("shared.telegram.kb_media")

_VIDEO_EXT = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm"})
_PHOTO_EXT = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})


async def send_vault_media_files(
    bot: Bot,
    chat_id: int,
    vault_path: Path,
    media_files: list[tuple[str, str]],
) -> None:
    """media_files: (rel_path in vault, caption)."""
    for file_rel, caption in media_files:
        file_path = (vault_path / file_rel).resolve()
        try:
            file_path.relative_to(vault_path.resolve())
        except ValueError:
            log.warning("skip media outside vault: %s", file_rel)
            continue
        if not file_path.is_file():
            log.warning("media file missing: %s", file_path)
            continue
        ext = file_path.suffix.lower()
        cap = (caption or "")[:1024]
        try:
            f = FSInputFile(str(file_path))
            if ext in _VIDEO_EXT:
                await bot.send_video(chat_id, f, caption=cap or None)
            elif ext in _PHOTO_EXT:
                await bot.send_photo(chat_id, f, caption=cap or None)
            else:
                await bot.send_document(chat_id, f, caption=cap or None)
            log.info("sent vault media: %s", file_rel)
        except Exception as e:
            log.warning("failed to send media %s: %s", file_rel, e)
