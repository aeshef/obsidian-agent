"""Planning domain: voice → ASR → same routing as text."""
from __future__ import annotations

import asyncio
import logging
import tempfile
import traceback
from pathlib import Path

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from planning_bot.app import keyboards
from planning_bot.app.handlers.commands import process_user_text
from planning_bot.core.config import BOT_DIR
from planning_bot.core.pdmsg import pdmsg
from planning_bot.services.asr import transcribe_from_config
from shared.agent.platform_config import platform_int
from shared.i18n import msg, msgf
from shared.telegram.voice import download_voice_file, safe_edit_status

log = logging.getLogger("planning_bot.voice")

_asr_sem: asyncio.Semaphore | None = None


def _get_asr_sem() -> asyncio.Semaphore:
    global _asr_sem
    if _asr_sem is None:
        _asr_sem = asyncio.Semaphore(1)
    return _asr_sem


async def transcribe_planning_voice(message: Message) -> str:
    voice = message.voice
    if not voice or not message.bot:
        return ""
    tmp_path = Path(tempfile.mktemp(suffix=".ogg"))
    try:
        await download_voice_file(message.bot, voice.file_id, tmp_path)
        async with _get_asr_sem():
            text = await asyncio.to_thread(
                transcribe_from_config,
                tmp_path,
                BOT_DIR / "config",
            )
        return (text or "").strip()
    finally:
        tmp_path.unlink(missing_ok=True)


async def handle_voice_message(
    self,
    message: Message,
    state: FSMContext,
    *,
    agent_app=None,
) -> None:
    preview_max = platform_int("telegram", "voice_preview_chars", default=400)
    status = await message.answer(msg("wire", "voice_transcribing"))
    try:
        text = await transcribe_planning_voice(message)
        if not text:
            await safe_edit_status(status, msg("wire", "voice_failed"))
            return
        preview = text if len(text) <= preview_max else text[:preview_max] + "…"
        await safe_edit_status(status, msgf("wire", "voice_preview", preview=preview))
        await process_user_text(self, message, state, text, agent_app=agent_app)
    except Exception as e:
        log.error("handle_voice_message failed: %s\n%s", e, traceback.format_exc())
        await message.answer(
            pdmsg("auto_8ea5aae503"),
            reply_markup=keyboards.get_main_keyboard(),
        )
