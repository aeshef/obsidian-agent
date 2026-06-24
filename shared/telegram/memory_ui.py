"""Memory panel text and inline keyboards (Telegram UI, config-driven)."""
from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from shared.agent.platform_config import platform_int
from shared.i18n import msg, msgf
from shared.memory import clear_all_history
from shared.memory.config import read_global_profile_excerpt_plain
from shared.memory.constants import AGENT_DOMAINS, GLOBAL_DOMAIN
from shared.memory.insight_format import (
    format_confirmed_ui_line,
    format_date_short,
    format_pending_ui_line,
    group_confirmed_records,
    normalize_kind,
)
from shared.memory.insights import get_store

_CB_OK = "mem:ok:"
_CB_NO = "mem:no:"
_CB_RESET = "mem:reset:"
_CB_OPEN = "mem:open"


def memory_open_callback() -> str:
    return _CB_OPEN


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


def _reset_keyboard() -> list[InlineKeyboardButton]:
    return [
        InlineKeyboardButton(
            text=msg("memory", "reset_session_btn"),
            callback_data=f"{_CB_RESET}session",
        ),
        InlineKeyboardButton(
            text=msg("memory", "reset_pending_btn"),
            callback_data=f"{_CB_RESET}pending",
        ),
        InlineKeyboardButton(
            text=msg("memory", "reset_confirmed_btn"),
            callback_data=f"{_CB_RESET}confirmed",
        ),
        InlineKeyboardButton(
            text=msg("memory", "reset_all_btn"),
            callback_data=f"{_CB_RESET}all",
        ),
    ]


def build_memory_keyboard(pending: list[dict]) -> InlineKeyboardMarkup:
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
    reset_row = _reset_keyboard()
    buttons.append(reset_row[:2])
    buttons.append(reset_row[2:])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_memory_panel(user_id: int, domain: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    store = get_store()
    store.prune_expired()
    pending = store.list_pending(user_id, domain)

    lines = [msg("memory", "title"), ""]

    profile = read_global_profile_excerpt_plain()
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
    lines.append(
        msgf(
            "memory",
            "layers_hint",
            reset_session=msg("memory", "reset_session_btn"),
            reset_pending=msg("memory", "reset_pending_btn"),
            reset_confirmed=msg("memory", "reset_confirmed_btn"),
        )
    )
    if pending:
        lines.append("")
        lines.append(msg("memory", "confirm_hint"))

    return "\n".join(lines), build_memory_keyboard(pending)


def apply_memory_reset(
    user_id: int,
    mode: str,
    domain: str | None = None,
) -> list[str]:
    """Apply reset mode; return user-facing result lines (i18n)."""
    if domain is not None and domain not in (*AGENT_DOMAINS, GLOBAL_DOMAIN):
        return [msg("memory", "reset_unknown_domain")]

    store = get_store()
    lines: list[str] = []
    if mode in ("session", "all"):
        clear_all_history(user_id)
        lines.append(msg("memory", "reset_session_done"))
    if mode in ("pending", "all"):
        n = store.clear_pending(user_id, domain)
        lines.append(msgf("memory", "reset_pending_done", count=n))
    if mode in ("confirmed", "all"):
        n = store.clear_confirmed(user_id, domain)
        lines.append(msgf("memory", "reset_confirmed_done", count=n))
    if not lines:
        return [msg("memory", "reset_unknown_mode")]
    return lines
