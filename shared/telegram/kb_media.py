"""Send media from vault (knowledge note attachments / dashboard charts)."""
from __future__ import annotations

import logging
from pathlib import Path

from aiogram import Bot
from aiogram.types import FSInputFile, InputMediaPhoto

log = logging.getLogger("shared.telegram.kb_media")

_VIDEO_EXT = frozenset({".mp4", ".mov", ".avi", ".mkv", ".webm"})
_PHOTO_EXT = frozenset({".jpg", ".jpeg", ".png", ".webp", ".gif"})


def _album_enabled() -> bool:
    try:
        from shared.agent.platform_config import platform_int

        return bool(platform_int("telegram", "media_album", default=1))
    except Exception:
        return True


def _album_max() -> int:
    try:
        from shared.agent.platform_config import platform_int

        return max(2, min(10, platform_int("telegram", "media_album_max", default=10)))
    except Exception:
        return 10


async def send_vault_media_files(
    bot: Bot,
    chat_id: int,
    vault_path: Path,
    media_files: list[tuple[str, str]],
) -> None:
    """media_files: (rel_path in vault, caption). Photos may be sent as Telegram albums."""
    vault_res = vault_path.resolve()
    photos: list[tuple[Path, str, str]] = []
    singles: list[tuple[Path, str, str]] = []

    for file_rel, caption in media_files:
        file_path = (vault_path / file_rel).resolve()
        try:
            file_path.relative_to(vault_res)
        except ValueError:
            log.warning("skip media outside vault: %s", file_rel)
            continue
        if not file_path.is_file():
            log.warning("media file missing: %s", file_path)
            continue
        ext = file_path.suffix.lower()
        cap = (caption or "")[:1024]
        if ext in _PHOTO_EXT:
            photos.append((file_path, cap, file_rel))
        else:
            singles.append((file_path, cap, file_rel))

    if _album_enabled() and len(photos) >= 2:
        max_n = _album_max()
        for i in range(0, len(photos), max_n):
            chunk = photos[i : i + max_n]
            media = []
            for idx, (path, cap, _rel) in enumerate(chunk):
                media.append(
                    InputMediaPhoto(
                        media=FSInputFile(str(path)),
                        caption=cap if idx == 0 and cap else None,
                    )
                )
            try:
                await bot.send_media_group(chat_id, media=media)
                log.info("sent vault media album: %s files", len(chunk))
            except Exception as e:
                log.warning("album send failed, falling back to singles: %s", e)
                for path, cap, rel in chunk:
                    await _send_one(bot, chat_id, path, cap, rel, photo=True)
    else:
        for path, cap, rel in photos:
            await _send_one(bot, chat_id, path, cap, rel, photo=True)

    for path, cap, rel in singles:
        ext = path.suffix.lower()
        await _send_one(
            bot,
            chat_id,
            path,
            cap,
            rel,
            photo=False,
            video=ext in _VIDEO_EXT,
        )


async def _send_one(
    bot: Bot,
    chat_id: int,
    file_path: Path,
    caption: str,
    file_rel: str,
    *,
    photo: bool,
    video: bool = False,
) -> None:
    try:
        f = FSInputFile(str(file_path))
        if video:
            await bot.send_video(chat_id, f, caption=caption or None)
        elif photo:
            await bot.send_photo(chat_id, f, caption=caption or None)
        else:
            await bot.send_document(chat_id, f, caption=caption or None)
        log.info("sent vault media: %s", file_rel)
    except Exception as e:
        log.warning("failed to send media %s: %s", file_rel, e)
