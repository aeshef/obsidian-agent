""" /memory command and insight callback verification (shared router for all bots)."""
from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from shared.agent.platform_config import platform_int
from shared.i18n import msg, msgf
from shared.memory import clear_all_history
from shared.memory.config import read_global_profile_excerpt
from shared.memory.constants import AGENT_DOMAINS, GLOBAL_DOMAIN
from shared.memory.insight_format import (
    format_confirmed_ui_line,
    format_date_short,
    format_pending_ui_line,
    group_confirmed_records,
    normalize_kind,
)
from shared.memory.insights import get_store

log = logging.getLogger("shared.telegram.memory")

memory_router = Router(name="agent_memory")

_CB_OK = "mem:ok:"
_CB_NO = "mem:no:"


def _collect_confirmed_records(user_id: int, domain: str | None) -> list[dict]:
    store = get_store()
    doms = [domain] if domain else ["global", *AGENT_DOMAINS]
    confirmed_limit = platform_int("memory_ui", "confirmed_list_max", default=12)
    records: list[dict] = []
    seen: set[tuple[str, str, str]] = set()
    for dom in doms:
        for row in store.read_confirmed_records(user_id, dom, limit=confirmed_limit):
            key = (
                dom,
                row.get("pattern_text") or "",
                row.get("confirmed_at") or "",
            )
            if key in seen:
                continue
            seen.add(key)
            records.append({**row, "domain": dom})
    return records


def _format_memory_list(user_id: int, domain: str | None) -> tuple[str, InlineKeyboardMarkup | None]:
    store = get_store()
    store.prune_expired()
    pending = store.list_pending(user_id, domain)

    lines = [msg("memory", "title"), ""]

    profile = read_global_profile_excerpt()
    lines.append(msg("memory", "profile_header"))
    lines.append(profile or msg("memory", "profile_unset"))
    lines.append("")

    pending_max = platform_int("memory_ui", "pending_list_max", default=10)
    if pending:
        lines.append(msg("memory", "pending_header"))
        for p in pending[:pending_max]:
            lines.append(
                format_pending_ui_line(
                    domain=p.get("domain", "?"),
                    date=format_date_short(p.get("created_at")),
                    kind=normalize_kind(p.get("kind")),
                    pid=int(p["id"]),
                    text=p.get("pattern_text", ""),
                    count=int(p.get("confirmations", 1)),
                )
            )
    else:
        lines.append(msg("memory", "no_pending"))

    records = _collect_confirmed_records(user_id, domain)
    durable, periodic = group_confirmed_records(records)
    confirmed_limit = platform_int("memory_ui", "confirmed_list_max", default=12)

    if durable:
        lines.append("")
        lines.append(msg("memory", "durable_header"))
        for row in durable[:confirmed_limit]:
            lines.append(
                format_confirmed_ui_line(
                    domain=row.get("domain", "?"),
                    date=format_date_short(row.get("confirmed_at")),
                    kind=normalize_kind(row.get("kind")),
                    text=row.get("pattern_text", ""),
                )
            )
    if periodic:
        lines.append("")
        lines.append(msg("memory", "periodic_header"))
        for row in periodic[:confirmed_limit]:
            lines.append(
                format_confirmed_ui_line(
                    domain=row.get("domain", "?"),
                    date=format_date_short(row.get("confirmed_at")),
                    kind=normalize_kind(row.get("kind")),
                    text=row.get("pattern_text", ""),
                )
            )
    if not durable and not periodic:
        lines.append("")
        lines.append(msg("memory", "no_confirmed"))

    lines.append("")
    lines.append(msg("memory", "layers_hint"))
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


@memory_router.message(Command("reset_memory"))
async def cmd_reset_memory(message: Message) -> None:
    parts = (message.text or "").split()
    mode = parts[1].strip().lower() if len(parts) > 1 else "session"
    domain = parts[2].strip().lower() if len(parts) > 2 else None
    if domain not in (*AGENT_DOMAINS, GLOBAL_DOMAIN, None):
        await message.answer(msg("memory", "reset_usage"))
        return

    store = get_store()
    lines: list[str] = []
    if mode in ("session", "all"):
        clear_all_history(message.chat.id)
        lines.append(msg("memory", "reset_session_done"))
    if mode in ("pending", "all"):
        n = store.clear_pending(message.chat.id, domain)
        lines.append(msgf("memory", "reset_pending_done", count=n))
    if mode in ("confirmed", "all"):
        n = store.clear_confirmed(message.chat.id, domain)
        lines.append(msgf("memory", "reset_confirmed_done", count=n))
    if not lines:
        lines.append(msg("memory", "reset_usage"))
    await message.answer("\n".join(lines))


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
