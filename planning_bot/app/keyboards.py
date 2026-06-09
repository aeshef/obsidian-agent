"""Planning reply keyboards (config/messages.{locale}.yaml)."""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from planning_bot.app.ui import pmsg_menu
from shared.telegram.keyboards import compact_keyboard_rows, reply_keyboard_from_rows


class ReplyKeyboardExtras:
    """Optional footer rows appended by a host process (e.g. unified bot).

    Standalone bots leave extras empty; a host calls ``set()`` once at startup.
    Domain keyboard builders call ``apply()`` before returning markup.
    """

    def __init__(self) -> None:
        self._rows: list[list[KeyboardButton]] = []

    def set(self, rows: list[list[KeyboardButton]] | None) -> None:
        self._rows = [list(row) for row in rows] if rows else []

    def clear(self) -> None:
        self._rows = []

    def apply(self, kb: ReplyKeyboardMarkup) -> ReplyKeyboardMarkup:
        if not self._rows:
            return kb
        existing = {btn.text for row in kb.keyboard for btn in row}
        extra: list[list[KeyboardButton]] = []
        for row in self._rows:
            if any(btn.text in existing for btn in row):
                continue
            extra.append(list(row))
        if not extra:
            return kb
        rows = [list(r) for r in kb.keyboard] + extra
        return ReplyKeyboardMarkup(
            keyboard=rows,
            resize_keyboard=kb.resize_keyboard,
            input_field_placeholder=kb.input_field_placeholder,
            selective=kb.selective,
            one_time_keyboard=kb.one_time_keyboard,
            is_persistent=kb.is_persistent,
        )


_keyboard_extras = ReplyKeyboardExtras()


def clear_keyboard_extras() -> None:
    _keyboard_extras.clear()


def set_keyboard_extras(rows: list[list[KeyboardButton]] | None) -> None:
    _keyboard_extras.set(rows)


def get_main_keyboard() -> ReplyKeyboardMarkup:
    from planning_bot.app.menu_gates import planning_auto_allowed
    from planning_bot.core.pdmsg import pdmsg
    from shared.capabilities.menu_actions_config import menu_main_keyboard_keys

    labels = [
        pdmsg(key)
        for key in menu_main_keyboard_keys("planning")
        if planning_auto_allowed(key) and pdmsg(key)
    ]
    rows = compact_keyboard_rows([labels] if labels else [])
    if rows:
        kb = reply_keyboard_from_rows(rows, resize_keyboard=True)
    else:
        kb = ReplyKeyboardMarkup(keyboard=[], resize_keyboard=True)
    return _keyboard_extras.apply(kb)


def append_button_rows(
    kb: ReplyKeyboardMarkup,
    rows: list[list[KeyboardButton | str]],
) -> ReplyKeyboardMarkup:
    """Append rows to a keyboard without touching global extras (one-off composition)."""
    normalized: list[list[KeyboardButton]] = []
    for row in rows:
        normalized.append([btn if isinstance(btn, KeyboardButton) else KeyboardButton(text=btn) for btn in row])
    extras = ReplyKeyboardExtras()
    extras.set(normalized)
    return extras.apply(kb)


def get_routines_keyboard() -> ReplyKeyboardMarkup:
    from planning_bot.core.pdmsg import pdmsg

    close_day = pdmsg("auto_checkin_close")
    rows_spec: list[list[str]] = [
        [
            pmsg_menu("routines_stats"),
            pmsg_menu("routines_recommendations"),
        ],
        [pmsg_menu("routines_today")],
    ]
    if close_day:
        rows_spec.append([close_day])
    rows_spec.append([pmsg_menu("back")])
    rows = compact_keyboard_rows(rows_spec)
    kb = reply_keyboard_from_rows(rows, resize_keyboard=True)
    return _keyboard_extras.apply(kb)


def get_tasks_filter_keyboard() -> ReplyKeyboardMarkup:
    rows = compact_keyboard_rows(
        [
            [pmsg_menu("goals"), pmsg_menu("priorities")],
            [pmsg_menu("statuses")],
            [pmsg_menu("all_tasks")],
            [pmsg_menu("back")],
        ]
    )
    kb = reply_keyboard_from_rows(rows, resize_keyboard=True)
    return _keyboard_extras.apply(kb)


def get_statuses_keyboard() -> ReplyKeyboardMarkup:
    from planning_bot.app.menu_gates import planning_submenu_allowed
    from planning_bot.core.config import KANBAN_COLUMNS

    rows: list[list[str | KeyboardButton]] = []
    if planning_submenu_allowed("kanban_column"):
        cols = KANBAN_COLUMNS
        for i in range(0, len(cols), 3):
            rows.append([cols[j] for j in range(i, min(i + 3, len(cols)))])
    rows.append([pmsg_menu("back")])
    kb = reply_keyboard_from_rows(compact_keyboard_rows(rows), resize_keyboard=True)
    return _keyboard_extras.apply(kb)


def get_categories_keyboard() -> ReplyKeyboardMarkup:
    from planning_bot.app.menu_gates import planning_submenu_allowed
    from planning_bot.core.config import CATEGORIES

    rows: list[list[str | KeyboardButton]] = []
    if planning_submenu_allowed("category"):
        prefix = pmsg_menu("category_prefix")
        for i in range(0, len(CATEGORIES), 2):
            row: list[str | KeyboardButton] = []
            for j in range(2):
                if i + j < len(CATEGORIES):
                    row.append(f"{prefix}{CATEGORIES[i + j]}")
            if row:
                rows.append(row)
    rows.append([pmsg_menu("back")])
    kb = reply_keyboard_from_rows(compact_keyboard_rows(rows), resize_keyboard=True)
    return _keyboard_extras.apply(kb)


def get_priorities_keyboard() -> ReplyKeyboardMarkup:
    from planning_bot.app.menu_gates import planning_submenu_allowed

    rows: list[list[str | KeyboardButton]] = []
    if planning_submenu_allowed("priority"):
        rows.extend(
            [
                [pmsg_menu("priority_high"), pmsg_menu("priority_medium")],
                [pmsg_menu("priority_low")],
            ]
        )
    rows.append([pmsg_menu("back")])
    kb = reply_keyboard_from_rows(compact_keyboard_rows(rows), resize_keyboard=True)
    return _keyboard_extras.apply(kb)
