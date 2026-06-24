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
from shared.memory.session import count_session_messages

_CB_OK = "mem:ok:"
_CB_NO = "mem:no:"
_CB_OPEN = "mem:open"
_CB_VIEW_MAIN = "mem:view:main"
_CB_VIEW_CLEAR = "mem:view:clear"
_CB_RESET_ASK = "mem:reset:ask:"
_CB_RESET_YES = "mem:reset:yes:"

_RESET_MODES = ("session", "pending", "confirmed", "all")


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


def _memory_counts(user_id: int, domain: str | None) -> tuple[int, int, int, int]:
    store = get_store()
    pending = store.list_pending(user_id, domain)
    records = _collect_confirmed_records(user_id, domain)
    durable, periodic = group_confirmed_records(records)
    return (
        count_session_messages(user_id),
        len(pending),
        len(durable),
        len(periodic),
    )


def _summary_block(user_id: int, domain: str | None) -> str:
    dialogue, pending_n, durable_n, periodic_n = _memory_counts(user_id, domain)
    lines = [msg("memory", "summary_header")]
    lines.append(msgf("memory", "summary_dialogue", count=dialogue))
    if pending_n:
        lines.append(msgf("memory", "summary_pending", count=pending_n))
    else:
        lines.append(msg("memory", "summary_pending_none"))
    if durable_n or periodic_n:
        lines.append(
            msgf(
                "memory",
                "summary_saved",
                durable=durable_n,
                periodic=periodic_n,
            )
        )
    else:
        lines.append(msg("memory", "summary_saved_none"))
    return "\n".join(lines)


def build_main_keyboard(pending: list[dict]) -> InlineKeyboardMarkup:
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
    buttons.append(
        [
            InlineKeyboardButton(
                text=msg("memory", "clear_menu_btn"),
                callback_data=_CB_VIEW_CLEAR,
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def build_clear_menu_keyboard(user_id: int) -> InlineKeyboardMarkup:
    dialogue, pending_n, durable_n, periodic_n = _memory_counts(user_id, None)
    rows = [
        [
            InlineKeyboardButton(
                text=msgf("memory", "clear_dialogue_btn", count=dialogue),
                callback_data=f"{_CB_RESET_ASK}session",
            ),
        ],
        [
            InlineKeyboardButton(
                text=msgf("memory", "clear_pending_btn", count=pending_n),
                callback_data=f"{_CB_RESET_ASK}pending",
            ),
        ],
        [
            InlineKeyboardButton(
                text=msgf("memory", "clear_confirmed_btn", count=durable_n + periodic_n),
                callback_data=f"{_CB_RESET_ASK}confirmed",
            ),
        ],
        [
            InlineKeyboardButton(
                text=msg("memory", "clear_all_btn"),
                callback_data=f"{_CB_RESET_ASK}all",
            ),
        ],
        [
            InlineKeyboardButton(
                text=msg("memory", "back_to_memory_btn"),
                callback_data=_CB_VIEW_MAIN,
            ),
        ],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_reset_confirm_keyboard(mode: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=msg("memory", "reset_yes_btn"),
                    callback_data=f"{_CB_RESET_YES}{mode}",
                ),
                InlineKeyboardButton(
                    text=msg("memory", "reset_cancel_btn"),
                    callback_data=_CB_VIEW_MAIN,
                ),
            ]
        ]
    )


def build_memory_panel(user_id: int, domain: str | None = None) -> tuple[str, InlineKeyboardMarkup]:
    store = get_store()
    store.prune_expired()
    pending = store.list_pending(user_id, domain)

    lines = [msg("memory", "title"), "", _summary_block(user_id, domain), ""]

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
        lines.append("")
        lines.append(msg("memory", "confirm_hint"))
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

    return "\n".join(lines), build_main_keyboard(pending)


def build_clear_menu_panel(user_id: int) -> tuple[str, InlineKeyboardMarkup]:
    dialogue, pending_n, durable_n, periodic_n = _memory_counts(user_id, None)
    text = "\n".join(
        [
            msg("memory", "clear_menu_title"),
            "",
            msg("memory", "clear_menu_hint"),
            "",
            msgf("memory", "summary_dialogue", count=dialogue),
            msgf("memory", "summary_pending", count=pending_n)
            if pending_n
            else msg("memory", "summary_pending_none"),
            msgf("memory", "summary_saved", durable=durable_n, periodic=periodic_n)
            if durable_n or periodic_n
            else msg("memory", "summary_saved_none"),
        ]
    )
    return text, build_clear_menu_keyboard(user_id)


def build_reset_confirm_panel(user_id: int, mode: str) -> tuple[str, InlineKeyboardMarkup]:
    if mode not in _RESET_MODES:
        return build_memory_panel(user_id)
    dialogue, pending_n, durable_n, periodic_n = _memory_counts(user_id, None)
    counts = {
        "session": dialogue,
        "pending": pending_n,
        "confirmed": durable_n + periodic_n,
        "all": dialogue + pending_n + durable_n + periodic_n,
    }
    key = f"reset_confirm_{mode}"
    text = msgf("memory", key, count=counts[mode])
    return text, build_reset_confirm_keyboard(mode)


def apply_memory_reset(
    user_id: int,
    mode: str,
    domain: str | None = None,
) -> list[str]:
    """Apply reset mode; return user-facing result lines (i18n)."""
    if mode not in _RESET_MODES:
        return [msg("memory", "reset_unknown_mode")]
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
