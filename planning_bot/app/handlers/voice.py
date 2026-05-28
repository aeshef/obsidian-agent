"""Voice file download + ASR helpers (aiogram)."""
from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from aiogram import Bot
from aiogram.types import Message

log = logging.getLogger("shared.telegram.voice")

_asr_sem: asyncio.Semaphore | None = None


def _get_asr_sem() -> asyncio.Semaphore:
    """One ASR at a time — do not block event loop or duplicate model in RAM."""
    global _asr_sem
    if _asr_sem is None:
        _asr_sem = asyncio.Semaphore(1)
    return _asr_sem


async def download_voice_file(bot: Bot, file_id: str, dest: Path) -> Path:
    """Download Telegram voice message to a temp file."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    tg_file = await bot.get_file(file_id)
    await bot.download_file(tg_file.file_path, destination=dest)
    return dest


async def transcribe_voice_message(message: Message) -> str:
    """ASR for voice message (non-blocking polling — CPU in thread pool)."""
    from bot.services.asr import transcribe_audio

    voice = message.voice
    if not voice or not message.bot:
        return ""
    tmp_path = Path(tempfile.mktemp(suffix=".ogg"))
    try:
        await download_voice_file(message.bot, voice.file_id, tmp_path)
        async with _get_asr_sem():
            text = await asyncio.to_thread(transcribe_audio, tmp_path)
        return (text or "").strip()
    finally:
        tmp_path.unlink(missing_ok=True)


async def safe_edit_status(status_msg: Message, text: str) -> None:
    """edit_text with fallback to answer (if polling restarted mid-ASR)."""
    try:
        await status_msg.edit_text(text)
    except Exception as e:
        log.warning("status edit failed (%s), sending new message", e)
        try:
            await status_msg.answer(text)
        except Exception:
            log.exception("status answer fallback failed")
