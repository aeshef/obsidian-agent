""" /memory command and insight callback verification (shared router for all bots)."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from shared.agent.platform_config import platform_int
from shared.i18n import msg, msgf
from shared.memory.insights import get_store

log = logging.getLogger("shared.telegram.memory")

memory_router = Router(name="agent_memory")

_CB_OK = "mem:ok:"
_CB_NO = "mem:no:"


def _format_memory_list(user_id: int, domain: str | None) -> tuple[str, InlineKeyboardMarkup | None]:
    store = get_store()
    pending = store.list_pending(user_id, domain)
    doms = [domain] if domain else ["global", "finance", "planning", "knowledge"]
    confirmed: list[str] = []
    seen: set[str] = set()
    confirmed_limit = platform_int("memory_ui", "confirmed_list_max", default=12)
    for d in doms:
        for p in store.read_confirmed(user_id, d, limit=confirmed_limit):
            if p not in seen:
                seen.add(p)
                confirmed.append(p)

    lines = [msg("memory", "title"), ""]
    pending_max = platform_int("memory_ui", "pending_list_max", default=10)
    if pending:
        lines.append(msg("memory", "pending_header"))
        for p in pending[:pending_max]:
            lines.append(
                msgf(
                    "memory",
                    "pending_line",
                    domain=p.get("domain", "?"),
                    id=p["id"],
                    text=p.get("pattern_text", ""),
                    count=p.get("confirmations", 1),
                )
            )
    else:
        lines.append(msg("memory", "no_pending"))

    if confirmed:
        lines.append("")
        lines.append(msg("memory", "confirmed_header"))
        for c in confirmed[:confirmed_limit]:
            lines.append(msgf("memory", "confirmed_line", text=c))
    else:
        lines.append("")
        lines.append(msg("memory", "no_confirmed"))

    lines.append("")
    lines.append(msg("memory", "confirm_hint"))

    buttons: list[list[InlineKeyboardButton]] = []
    buttons_max = platform_int("memory_ui", "pending_buttons_max", default=8)
    for p in pending[:buttons_max]:
        pid = p["id"]
        buttons.append(
            [
                InlineKeyboardButton(
                    text=msgf("memory", "confirm_btn", id=pid),
                    callback_data=f"{_CB_OK}{pid}",
                ),
                InlineKeyboardButton(
                    text=msgf("memory", "reject_btn", id=pid),
                    callback_data=f"{_CB_NO}{pid}",
                ),
            ]
        )
    markup = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    return "\n".join(lines), markup


@memory_router.message(Command("memory"))
async def cmd_memory(message: Message) -> None:
    domain = (message.text or "").split(maxsplit=1)
    dom_filter = None
    if len(domain) > 1 and domain[1].strip().lower() in ("finance", "planning", "knowledge"):
        dom_filter = domain[1].strip().lower()
    text, markup = _format_memory_list(message.chat.id, dom_filter)
    await message.answer(text, reply_markup=markup)


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
        text, markup = _format_memory_list(callback.message.chat.id, None)
        await callback.message.edit_text(text, reply_markup=markup)


@memory_router.callback_query(F.data == "mem:noop")
async def cb_noop(callback: CallbackQuery) -> None:
    await callback.answer(msg("memory", "open_memory"))


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
        text, markup = _format_memory_list(callback.message.chat.id, None)
        await callback.message.edit_text(text, reply_markup=markup)
