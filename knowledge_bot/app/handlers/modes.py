"""Bulk ingest and query mode buttons."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from aiogram.types import Message

from knowledge_bot.app.ui import kmsg
from knowledge_bot.app.state import (
    BTN_BULK_OFF,
    BTN_BULK_ON,
    BTN_QUERY,
    bulk_session_stats,
    is_bulk_ingest,
    main_reply_keyboard,
    set_bulk_ingest,
)

if TYPE_CHECKING:
    from aiogram.fsm.context import FSMContext


async def enable_bulk_ingest(
    message: Message,
    reply_markup=None,
    state: Optional["FSMContext"] = None,
) -> None:
    uid = message.from_user.id if message.from_user else 0
    set_bulk_ingest(uid, True)
    if state is not None:
        from shared.telegram.host.constants import DOMAIN_KNOWLEDGE

        await state.update_data(bulk_ingest=True, ui_mode=DOMAIN_KNOWLEDGE)
    kb = reply_markup or main_reply_keyboard(bulk_active=True)
    await message.answer(kmsg("bulk_enabled"), reply_markup=kb)


async def disable_bulk_ingest(
    message: Message,
    reply_markup=None,
    state: Optional["FSMContext"] = None,
) -> None:
    uid = message.from_user.id if message.from_user else 0
    stats = set_bulk_ingest(uid, False)
    if state is not None:
        await state.update_data(bulk_ingest=False)
    kb = reply_markup or main_reply_keyboard(bulk_active=False)
    await message.answer(
        kmsg("bulk_disabled", saved=stats["saved"], failed=stats["failed"]),
        reply_markup=kb,
    )


async def try_handle_mode_button(message: Message) -> bool:
    """True when a mode reply-keyboard button was handled."""
    text = (message.text or "").strip()
    if not text or not message.from_user:
        return False
    uid = message.from_user.id

    if text == BTN_BULK_ON:
        await enable_bulk_ingest(message)
        return True

    if text == BTN_BULK_OFF:
        await disable_bulk_ingest(message)
        return True

    if text == BTN_QUERY:
        await message.answer(
            kmsg("query_prompt"),
            reply_markup=main_reply_keyboard(bulk_active=is_bulk_ingest(uid)),
        )
        return True

    return False
