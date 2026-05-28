from __future__ import annotations

import asyncio
import os
from typing import Any

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from knowledge_bot.app import kb_labels as kb_lbl

BTN_BULK_ON = kb_lbl.bulk_on()
BTN_BULK_OFF = kb_lbl.bulk_off()
BTN_QUERY = kb_lbl.query_button()

_BULK_INGEST: set[int] = set()
_BULK_SESSION: dict[int, dict[str, int]] = {}  # user_id -> {saved, failed, ack}


def is_bulk_ingest(user_id: int | None) -> bool:
    return bool(user_id and user_id in _BULK_INGEST)


def activate_bulk_ingest(user_id: int) -> None:
    """Enable bulk ingest in RAM."""
    _BULK_INGEST.add(user_id)


def set_bulk_ingest(user_id: int, enabled: bool) -> dict[str, int]:
    if enabled:
        activate_bulk_ingest(user_id)
        _BULK_SESSION[user_id] = {"saved": 0, "failed": 0, "ack": 0}
        return dict(_BULK_SESSION[user_id])
    stats = bulk_session_stats(user_id)
    _BULK_INGEST.discard(user_id)
    return stats


def bulk_take_processing_ack(user_id: int) -> bool:
    """True once per session: show processing ack to user."""
    if not is_bulk_ingest(user_id):
        return False
    st = _BULK_SESSION.setdefault(user_id, {"saved": 0, "failed": 0, "ack": 0})
    if st.get("ack"):
        return False
    st["ack"] = 1
    return True


def bulk_session_stats(user_id: int) -> dict[str, int]:
    st = _BULK_SESSION.get(user_id, {"saved": 0, "failed": 0})
    return {"saved": int(st.get("saved", 0)), "failed": int(st.get("failed", 0))}


def bulk_record_saved(user_id: int) -> None:
    st = _BULK_SESSION.setdefault(user_id, {"saved": 0, "failed": 0})
    st["saved"] = st.get("saved", 0) + 1


def bulk_record_failed(user_id: int) -> None:
    st = _BULK_SESSION.setdefault(user_id, {"saved": 0, "failed": 0})
    st["failed"] = st.get("failed", 0) + 1


def main_reply_keyboard(*, bulk_active: bool) -> ReplyKeyboardMarkup:
    b = ReplyKeyboardBuilder()
    if bulk_active:
        b.row(KeyboardButton(text=BTN_BULK_OFF))
    else:
        b.row(KeyboardButton(text=BTN_BULK_ON))
    b.row(KeyboardButton(text=BTN_QUERY))
    return b.as_markup(resize_keyboard=True)


_PENDING: dict[int, dict[str, Any]] = {}
# PENDING_LIMIT env caps in-memory preview queue size


def pending_limit() -> int:
    return int(os.environ.get("PENDING_LIMIT", "100"))


_MEDIA_GROUPS: dict[int, dict[str, Any]] = {}  # media_group_id -> {"messages": [...], "processing": bool, "processed": bool}
_RECENT_REVIEWS: dict[int, float] = {}

# Semaphores (initialized in main())
_PROCESSING_SEMAPHORE: asyncio.Semaphore | None = None
_MESSAGE_RATE_LIMITER: asyncio.Semaphore | None = None
_ASR_SEMAPHORE: asyncio.Semaphore | None = None


def get_processing_semaphore() -> asyncio.Semaphore:
    """Serial message processing semaphore (low RAM / heavy pipeline)."""
    global _PROCESSING_SEMAPHORE
    if _PROCESSING_SEMAPHORE is None:
        _PROCESSING_SEMAPHORE = asyncio.Semaphore(1)
    return _PROCESSING_SEMAPHORE


def get_message_rate_limiter() -> asyncio.Semaphore:
    """Outbound message rate limiter."""
    global _MESSAGE_RATE_LIMITER
    if _MESSAGE_RATE_LIMITER is None:
        _MESSAGE_RATE_LIMITER = asyncio.Semaphore(1)
    return _MESSAGE_RATE_LIMITER


def get_asr_semaphore() -> asyncio.Semaphore:
    """Single concurrent ASR job (OOM guard)."""
    global _ASR_SEMAPHORE
    if _ASR_SEMAPHORE is None:
        _ASR_SEMAPHORE = asyncio.Semaphore(1)
    return _ASR_SEMAPHORE


async def cleanup_media_group_after_delay(media_group_id: int, delay: float = 60.0) -> None:
    """Drop media_group from memory after delay seconds."""
    await asyncio.sleep(delay)
    _MEDIA_GROUPS.pop(media_group_id, None)


def preview_keyboard() -> InlineKeyboardBuilder:
    kb = InlineKeyboardBuilder()
    kb.button(text=kb_lbl.preview_save(), callback_data="save")
    kb.button(text=kb_lbl.preview_type(), callback_data="type")
    kb.button(text=kb_lbl.preview_cancel(), callback_data="cancel")
    kb.adjust(3)
    return kb
