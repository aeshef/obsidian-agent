"""User-facing strings live in YAML configs."""
from __future__ import annotations

import logging

from aiogram import Dispatcher, F
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder

from knowledge_bot.app.ui import kmsg
from knowledge_bot.core.config import load_config
from knowledge_bot.core.settings import load_types_config

from . import state as app_state
from .handlers.set_type import on_set_type
from .save_note import commit_routed_note
from .state import pending_limit, preview_keyboard

log = logging.getLogger("kb.register")


def register_knowledge_callbacks(dp: Dispatcher) -> None:
    async def on_cancel(cb: CallbackQuery):
        app_state._PENDING.pop(cb.message.message_id, None)
        await cb.message.edit_text(kmsg("cancelled"))
        try:
            await cb.answer()
        except TelegramBadRequest:
            pass

    async def on_save(cb: CallbackQuery):
        cfg_l = load_config()
        st = app_state._PENDING.get(cb.message.message_id)
        if not st:
            await cb.answer(
                kmsg("pending_data_lost", limit=pending_limit()),
                show_alert=True,
            )
            return
        try:
            note_path = commit_routed_note(st["payload"], st.get("summary"))
        except Exception as e:
            log.error("Failed to save note: %s", e)
            await cb.answer(kmsg("save_error"), show_alert=True)
            return
        app_state._PENDING.pop(cb.message.message_id, None)
        payload = st["payload"]
        await cb.message.edit_text(
            kmsg(
                "note_created",
                path=note_path.relative_to(cfg_l.vault_path),
                type=payload["type"],
            )
        )
        try:
            await cb.answer()
        except TelegramBadRequest:
            pass

    async def on_type_menu(cb: CallbackQuery):
        cfg_l = load_config()
        types_cfg = load_types_config(cfg_l.agent_config_path)
        keys = list(types_cfg.types.keys())
        page = 0
        per_page = 6
        start = page * per_page
        slice_keys = keys[start : start + per_page]
        kb = InlineKeyboardBuilder()
        for k in slice_keys:
            kb.button(text=f"🔖 {k}", callback_data=f"set_type:{k}")
        if start > 0:
            kb.button(text="◀️", callback_data=f"types:{page-1}")
        if start + per_page < len(keys):
            kb.button(text="▶️", callback_data=f"types:{page+1}")
        kb.button(text=kmsg("back_button"), callback_data="back")
        kb.adjust(3)
        await cb.message.edit_text(kmsg("pick_type_page_one"), reply_markup=kb.as_markup())
        try:
            await cb.answer()
        except TelegramBadRequest:
            pass

    async def on_back(cb: CallbackQuery):
        st = app_state._PENDING.get(cb.message.message_id)
        if not st:
            try:
                await cb.answer()
            except TelegramBadRequest:
                pass
            return
        await cb.message.edit_text(
            kmsg(
                "preview_ready_typed",
                type=st["payload"]["type"],
                title=st["payload"]["title"],
            ),
            reply_markup=preview_keyboard().as_markup(),
        )
        try:
            await cb.answer()
        except TelegramBadRequest:
            pass

    async def on_types_page(cb: CallbackQuery):
        cfg_l = load_config()
        types_cfg = load_types_config(cfg_l.agent_config_path)
        keys = list(types_cfg.types.keys())
        try:
            page = int(cb.data.split(":", 1)[1])
        except Exception:
            page = 0
        per_page = 6
        total_pages = (len(keys) + per_page - 1) // per_page
        page = max(0, min(page, max(0, total_pages - 1)))
        start = page * per_page
        slice_keys = keys[start : start + per_page]
        kb = InlineKeyboardBuilder()
        for k in slice_keys:
            kb.button(text=f"🔖 {k}", callback_data=f"set_type:{k}")
        if page > 0:
            kb.button(text="◀️", callback_data=f"types:{page-1}")
        if page + 1 < total_pages:
            kb.button(text="▶️", callback_data=f"types:{page+1}")
        kb.button(text=kmsg("back_button"), callback_data="back")
        kb.adjust(3)
        await cb.message.edit_text(
            kmsg("pick_type_page", page=page + 1, total=total_pages),
            reply_markup=kb.as_markup(),
        )
        try:
            await cb.answer()
        except TelegramBadRequest:
            pass

    dp.callback_query.register(on_cancel, F.data == "cancel")
    dp.callback_query.register(on_save, F.data == "save")
    dp.callback_query.register(on_type_menu, F.data == "type")
    dp.callback_query.register(on_set_type, F.data.startswith("set_type:"))
    dp.callback_query.register(on_types_page, F.data.startswith("types:"))
    dp.callback_query.register(on_back, F.data == "back")
