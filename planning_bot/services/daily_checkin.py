"""Daily close orchestrator: routines queue + subjective signals."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from planning_bot.app.ui import pmsg
from planning_bot.core.config import CATEGORIES, category_emoji
from planning_bot.services.daily_checkin_config import (
    routine_sections_order,
    scales_config,
    skip_already_checked_routines,
    signals_config,
)
from planning_bot.services.routines_manager import load_tasks_config, load_today_status, set_task_done


@dataclass(frozen=True)
class RoutineItem:
    section: str
    task: str
    already_done: bool


@dataclass(frozen=True)
class SignalItem:
    signal_id: str
    kind: str
    scale: str | None
    question_key: str


def build_routine_queue() -> list[RoutineItem]:
    morning, day, evening = load_tasks_config()
    pools = {"morning": morning, "day": day, "evening": evening}
    status = load_today_status()
    out: list[RoutineItem] = []
    for section in routine_sections_order():
        tasks = pools.get(section) or []
        for task in tasks:
            done = bool(status.get(section, {}).get(task, False))
            if skip_already_checked_routines() and done:
                continue
            out.append(RoutineItem(section=section, task=task, already_done=done))
    return out


def build_signal_queue() -> list[SignalItem]:
    out: list[SignalItem] = []
    for raw in signals_config():
        sid = str(raw.get("id", "")).strip()
        if not sid:
            continue
        if raw.get("type") == "category_choice":
            out.append(
                SignalItem(
                    signal_id=sid,
                    kind="category_choice",
                    scale=None,
                    question_key=str(raw.get("question_key", f"checkin_signal_{sid}")),
                )
            )
        else:
            out.append(
                SignalItem(
                    signal_id=sid,
                    kind="scale",
                    scale=str(raw.get("scale", "likert_5")),
                    question_key=str(raw.get("question_key", f"checkin_signal_{sid}")),
                )
            )
    return out


def section_label(section: str) -> str:
    key = {
        "morning": "checkin_section_morning",
        "day": "checkin_section_day",
        "evening": "checkin_section_evening",
    }.get(section, "checkin_section_other")
    return pmsg(key)


def routine_prompt_text(item: RoutineItem, index: int, total: int) -> str:
    return pmsg(
        "checkin_routine_prompt",
        section=section_label(item.section),
        task=item.task,
        index=index,
        total=total,
    )


def signal_prompt_text(item: SignalItem) -> str:
    return pmsg(item.question_key)


def routine_keyboard(section: str, task_index: int) -> InlineKeyboardMarkup:
    sec = section[:1]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=pmsg("checkin_btn_done"),
                    callback_data=f"chk:r:{sec}:{task_index}:1",
                ),
                InlineKeyboardButton(
                    text=pmsg("checkin_btn_skip"),
                    callback_data=f"chk:r:{sec}:{task_index}:0",
                ),
            ],
            [
                InlineKeyboardButton(
                    text=pmsg("checkin_btn_skip_section"),
                    callback_data=f"chk:rs:{sec}",
                ),
            ],
        ]
    )


def offer_keyboard() -> InlineKeyboardMarkup:
    from planning_bot.services.ritual_day import calendar_day_date, ritual_day_active, ritual_day_date

    ritual = ritual_day_date()
    rows: list[list[InlineKeyboardButton]] = []
    if ritual_day_active():
        cal = calendar_day_date()
        rows.append(
            [
                InlineKeyboardButton(
                    text=pmsg("checkin_btn_start_date", date=ritual),
                    callback_data="chk:go",
                ),
                InlineKeyboardButton(
                    text=pmsg("checkin_btn_start_calendar", date=cal),
                    callback_data=f"chk:gd:{cal}",
                ),
            ]
        )
        rows.append(
            [
                InlineKeyboardButton(
                    text=pmsg("checkin_btn_later"),
                    callback_data="chk:snooze",
                ),
            ]
        )
    else:
        rows.append(
            [
                InlineKeyboardButton(
                    text=pmsg("checkin_btn_start"),
                    callback_data="chk:go",
                ),
                InlineKeyboardButton(
                    text=pmsg("checkin_btn_later"),
                    callback_data="chk:snooze",
                ),
            ]
        )
    rows.append(
        [
            InlineKeyboardButton(
                text=pmsg("checkin_btn_skip_today"),
                callback_data="chk:skip",
            ),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def scale_keyboard(signal_index: int, scale_id: str) -> InlineKeyboardMarkup:
    scales = scales_config()
    spec = scales.get(scale_id) if isinstance(scales.get(scale_id), dict) else {}
    values = list(spec.get("values") or [])
    label_keys = list(spec.get("label_keys") or [])
    row: list[InlineKeyboardButton] = []
    rows: list[list[InlineKeyboardButton]] = []
    for i, val in enumerate(values):
        label_key = label_keys[i] if i < len(label_keys) else f"checkin_scale_value_{val}"
        label = pmsg(label_key)
        row.append(
            InlineKeyboardButton(
                text=label,
                callback_data=f"chk:s:{signal_index}:{val}",
            )
        )
        if len(row) >= 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def category_keyboard(signal_index: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, cat in enumerate(CATEGORIES):
        emoji = category_emoji(cat)
        row.append(
            InlineKeyboardButton(
                text=f"{emoji} {cat}",
                callback_data=f"chk:c:{signal_index}:{i}",
            )
        )
        if len(row) >= 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return InlineKeyboardMarkup(inline_keyboard=rows)


def apply_routine_answer(
    queue: list[RoutineItem],
    index: int,
    done: bool,
) -> bool:
    if index < 0 or index >= len(queue):
        return False
    item = queue[index]
    return set_task_done(item.section, item.task, done)


def resolve_category_index(index: int) -> str:
    if 0 <= index < len(CATEGORIES):
        return CATEGORIES[index]
    return CATEGORIES[0] if CATEGORIES else "other"


def completion_summary(signal_answers: dict[str, Any], close_date: str) -> str:
    lines = [pmsg("checkin_complete_title", date=close_date)]
    if signal_answers:
        lines.append(pmsg("checkin_complete_signals_saved", date=close_date))
    return "\n".join(lines)
