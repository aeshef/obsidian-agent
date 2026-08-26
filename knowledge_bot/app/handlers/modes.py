"""Bulk ingest and query mode buttons."""
from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from aiogram.types import Message

from knowledge_bot.app.ui import kmsg
from knowledge_bot.app.state import (
    bulk_session_stats,
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
        from unified_bot.host.constants import DOMAIN_KNOWLEDGE
        from unified_bot.host.keyboards import knowledge_keyboard

        await state.update_data(bulk_ingest=True, ui_mode=DOMAIN_KNOWLEDGE)
        kb = knowledge_keyboard(bulk_active=True)
    else:
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
        from unified_bot.host.constants import DOMAIN_IDS, DOMAIN_KNOWLEDGE
        from unified_bot.host.keyboards import keyboard_for_mode

        await state.update_data(bulk_ingest=False)
        data = await state.get_data()
        ui_mode = data.get("ui_mode", DOMAIN_KNOWLEDGE)
        kb_mode = ui_mode if ui_mode in DOMAIN_IDS else DOMAIN_KNOWLEDGE
        kb = keyboard_for_mode(kb_mode, user_id=uid)
    else:
        kb = reply_markup or main_reply_keyboard(bulk_active=False)
    await message.answer(
        kmsg("bulk_disabled", saved=stats["saved"], failed=stats["failed"]),
        reply_markup=kb,
    )


async def try_handle_mode_button(message: Message) -> bool:
    """True when a mode reply-keyboard button was handled."""
    from knowledge_bot.app.menu_dispatch import dispatch_knowledge_menu_button

    return await dispatch_knowledge_menu_button(message)
