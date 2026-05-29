"""Composable reply keyboards for Telegram bots."""
from __future__ import annotations

from aiogram.types import KeyboardButton, ReplyKeyboardMarkup


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
