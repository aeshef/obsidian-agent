"""Memory panel and insight callbacks (shared router for all bots)."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from shared.i18n import msg
from shared.telegram.memory_ui import (
    _CB_NO,
    _CB_OK,
    _CB_OPEN,
    _CB_RESET_ASK,
    _CB_RESET_YES,
    _CB_VIEW_CLEAR,
    _CB_VIEW_MAIN,
    apply_memory_reset,
    build_clear_menu_panel,
    build_memory_panel,
    build_reset_confirm_panel,
    memory_open_callback,
)
from shared.telegram.messaging import send_long_message
from shared.memory.insights import get_store

log = logging.getLogger("shared.telegram.memory")

memory_router = Router(name="agent_memory")


async def send_memory_panel(message: Message, domain: str | None = None) -> None:
    text, markup = build_memory_panel(message.chat.id, domain)
    await send_long_message(
        message.bot, message.chat.id, text, reply_markup=markup, rich=False
    )


async def _edit_memory_panel(callback: CallbackQuery, *, text: str, markup) -> None:
    if not callback.message:
        return
    await callback.message.edit_text(text, reply_markup=markup)


@memory_router.callback_query(F.data == _CB_OPEN)
async def cb_open_memory(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message:
        return
    text, markup = build_memory_panel(callback.message.chat.id)
    await send_long_message(
        callback.message.bot,
        callback.message.chat.id,
        text,
        reply_markup=markup,
        rich=False,
    )


@memory_router.callback_query(F.data == _CB_VIEW_MAIN)
async def cb_view_main(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message:
        return
    text, markup = build_memory_panel(callback.message.chat.id)
    await _edit_memory_panel(callback, text=text, markup=markup)


@memory_router.callback_query(F.data == _CB_VIEW_CLEAR)
async def cb_view_clear(callback: CallbackQuery) -> None:
    await callback.answer()
    if not callback.message:
        return
    text, markup = build_clear_menu_panel(callback.message.chat.id)
    await _edit_memory_panel(callback, text=text, markup=markup)


@memory_router.callback_query(F.data.startswith(_CB_RESET_ASK))
async def cb_reset_ask(callback: CallbackQuery) -> None:
    mode = (callback.data or "")[len(_CB_RESET_ASK) :].strip().lower()
    if not callback.message:
        await callback.answer(msg("memory", "reset_unknown_mode"), show_alert=True)
        return
    await callback.answer()
    text, markup = build_reset_confirm_panel(callback.message.chat.id, mode)
    await _edit_memory_panel(callback, text=text, markup=markup)


@memory_router.callback_query(F.data.startswith(_CB_RESET_YES))
async def cb_reset_yes(callback: CallbackQuery) -> None:
    mode = (callback.data or "")[len(_CB_RESET_YES) :].strip().lower()
    if not callback.message:
        await callback.answer(msg("memory", "reset_unknown_mode"), show_alert=True)
        return
    lines = apply_memory_reset(callback.message.chat.id, mode)
    await callback.answer("\n".join(lines)[:200])
    text, markup = build_memory_panel(callback.message.chat.id)
    await _edit_memory_panel(callback, text=text, markup=markup)


@memory_router.callback_query(F.data.startswith(_CB_OK))
async def cb_confirm(callback: CallbackQuery) -> None:
    try:
        pid = int((callback.data or "")[len(_CB_OK) :])
    except ValueError:
        await callback.answer(msg("memory", "invalid_id"), show_alert=True)
        return
    ok = get_store().confirm(pid)
    if ok:
        await callback.answer(msg("memory", "saved"))
    else:
        await callback.answer(msg("memory", "not_found"), show_alert=True)
    if callback.message:
        text, markup = build_memory_panel(callback.message.chat.id)
        await _edit_memory_panel(callback, text=text, markup=markup)


@memory_router.callback_query(F.data.startswith(_CB_NO))
async def cb_reject(callback: CallbackQuery) -> None:
    try:
        pid = int((callback.data or "")[len(_CB_NO) :])
    except ValueError:
        await callback.answer(msg("memory", "invalid_id"), show_alert=True)
        return
    ok = get_store().reject(pid)
    await callback.answer(
        msg("memory", "rejected") if ok else msg("memory", "not_found"),
        show_alert=not ok,
    )
    if callback.message:
        text, markup = build_memory_panel(callback.message.chat.id)
        await _edit_memory_panel(callback, text=text, markup=markup)
