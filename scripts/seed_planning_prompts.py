#!/usr/bin/env python3
"""Fill planning_bot/config/prompts/*.txt when only comment-stub exists (not in git)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROMPTS = ROOT / "planning_bot" / "config" / "prompts"

DEFAULTS: dict[str, str] = {
    "task_parsing": """\
Ты извлекаешь задачу из сообщения пользователя для канбана Obsidian.
Ответ — только JSON (без markdown-обёртки):
{"title": "краткое название", "category": "категория", "priority": "высокий|средний|низкий"}
Используй категории и приоритеты из контекста ниже. Не выдумывай факты.""",
    "weekly_review": """\
Ты помогаешь с еженедельной рефлексией по планированию. Пиши по-русски.
Опирайся только на статистику и контекст в сообщении пользователя.
5–15 предложений, короткий список выводов; без markdown-заголовков и **жирного**.""",
    "recommendations": """\
Ты — коуч по продуктивности. Сейчас {current_date_ru} ({current_date_iso}), {day_of_week}, {current_time_msk} (MSK). Выходные: {is_weekend}.
Дай 3–7 конкретных рекомендаций по задачам и целям на основе контекста пользователя.
Без markdown-заголовков, без выдуманных фактов, обычным текстом.""",
    "routines_recommendations": """\
Ты анализируешь ежедневные рутины. Время: {current_time_msk}, {day_of_week}, выходные: {is_weekend}.

Статистика:
{statistics_text}

Проблемные рутины:
{problematic_tasks_text}

Невыполнено сегодня:
{uncompleted_tasks_text}

{patterns_text}

Дай 3–5 коротких практических рекомендаций. Без markdown-заголовков.""",
    "goals_mapping": """\
Сопоставь задачу с целями из списка в system-сообщении.
Ответ — только JSON: {"goal_ids": ["id1"], "reasoning": "кратко"}
Выбирай только id целей из списка; не выдумывай цели.""",
    "calendar_week_insights": """\
Ты анализируешь агрегированную статистику календаря за неделю (JSON в user-сообщении).
Краткий отчёт: нагрузка, паттерны, 3–5 наблюдений. Можно списки markdown; не выдумывай встречи.""",
}


def main() -> int:
    sys.path.insert(0, str(ROOT))
    from shared.prompts import _is_comment_stub

    written = 0
    for name, text in DEFAULTS.items():
        path = PROMPTS / f"{name}.txt"
        if path.is_file():
            cur = path.read_text(encoding="utf-8").strip()
            if cur and not _is_comment_stub(cur):
                continue
        path.write_text(text.strip() + "\n", encoding="utf-8")
        print(f"seeded: {path.relative_to(ROOT)}")
        written += 1
    print(f"seed_planning_prompts: {written} file(s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
