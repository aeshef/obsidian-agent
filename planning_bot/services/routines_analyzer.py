from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from planning_bot.services.routines_config import SECTION_ORDER, section_history_label
from planning_bot.services.routines_manager import (
    get_today_date,
    get_today_date_from_state,
    load_tasks_config,
    load_today_status,
)
from shared.routines_paths import routines_history_path
from shared.tz import get_tz


def get_current_local_time() -> datetime:
    """Now in TIMEZONE / CALENDAR_TZ (legacy alias: get_current_time_msk)."""
    return datetime.now(get_tz())


def get_current_time_msk() -> datetime:
    return get_current_local_time()


def parse_history() -> Dict[str, Dict[str, Dict[str, bool]]]:
    path = routines_history_path()
    if not path.is_file():
        return {}

    content = path.read_text(encoding="utf-8")
    lines = content.split("\n")

    stats: dict[str, dict[str, dict[str, bool]]] = {}
    current_date: str | None = None
    current_section: str | None = None

    for line in lines:
        date_match = re.match(r"^## (\d{4}-\d{2}-\d{2})", line)
        if date_match:
            current_date = date_match[1]
            stats[current_date] = {"morning": {}, "day": {}, "evening": {}}
            current_section = None
            continue

        for section in SECTION_ORDER:
            if section_history_label(section) in line:
                current_section = section
                break
        else:
            if current_date and current_section:
                task_match = re.match(r"^-\s*(✅|⬜)\s*(.+)$", line)
                if task_match:
                    is_done = task_match.group(1) == "✅"
                    task = task_match.group(2).strip()
                    stats[current_date][current_section][task] = is_done

    return stats


def get_statistics(days: int = 30) -> Dict:
    morning_tasks, day_tasks, evening_tasks = load_tasks_config()
    history = parse_history()

    now_msk = get_current_time_msk()
    cutoff_date = (now_msk - timedelta(days=days)).strftime("%Y-%m-%d")

    filtered_history = {date: data for date, data in history.items() if date >= cutoff_date}

    task_stats: dict[str, dict] = {}

    for task in morning_tasks:
        completed = 0
        total = 0
        for date_data in filtered_history.values():
            if task in date_data.get("morning", {}):
                total += 1
                if date_data["morning"][task]:
                    completed += 1
        task_stats[f"morning:{task}"] = {
            "task": task,
            "section": "morning",
            "completed": completed,
            "total": total,
            "percent": round((completed / total * 100) if total > 0 else 0, 1),
        }

    for task in evening_tasks:
        completed = 0
        total = 0
        for date_data in filtered_history.values():
            if task in date_data.get("evening", {}):
                total += 1
                if date_data["evening"][task]:
                    completed += 1
        task_stats[f"evening:{task}"] = {
            "task": task,
            "section": "evening",
            "completed": completed,
            "total": total,
            "percent": round((completed / total * 100) if total > 0 else 0, 1),
        }

    for task in day_tasks:
        completed = 0
        total = 0
        for date_data in filtered_history.values():
            if task in date_data.get("day", {}):
                total += 1
                if date_data["day"][task]:
                    completed += 1
        task_stats[f"day:{task}"] = {
            "task": task,
            "section": "day",
            "completed": completed,
            "total": total,
            "percent": round((completed / total * 100) if total > 0 else 0, 1),
        }

    total_morning_completed = sum(s["completed"] for k, s in task_stats.items() if k.startswith("morning:"))
    total_morning_possible = sum(s["total"] for k, s in task_stats.items() if k.startswith("morning:"))
    morning_percent = round(
        (total_morning_completed / total_morning_possible * 100) if total_morning_possible > 0 else 0,
        1,
    )

    total_evening_completed = sum(s["completed"] for k, s in task_stats.items() if k.startswith("evening:"))
    total_evening_possible = sum(s["total"] for k, s in task_stats.items() if k.startswith("evening:"))
    evening_percent = round(
        (total_evening_completed / total_evening_possible * 100) if total_evening_possible > 0 else 0,
        1,
    )

    total_day_completed = sum(s["completed"] for k, s in task_stats.items() if k.startswith("day:"))
    total_day_possible = sum(s["total"] for k, s in task_stats.items() if k.startswith("day:"))
    day_percent = round((total_day_completed / total_day_possible * 100) if total_day_possible > 0 else 0, 1)

    return {
        "days_analyzed": days,
        "total_days": len(filtered_history),
        "task_stats": task_stats,
        "morning_percent": morning_percent,
        "day_percent": day_percent,
        "evening_percent": evening_percent,
        "total_morning_completed": total_morning_completed,
        "total_morning_possible": total_morning_possible,
        "total_day_completed": total_day_completed,
        "total_day_possible": total_day_possible,
        "total_evening_completed": total_evening_completed,
        "total_evening_possible": total_evening_possible,
    }


def get_problematic_tasks(days: int = 7, min_failures: int = 3) -> List[Dict]:
    stats = get_statistics(days=days)
    problematic: list[dict] = []

    for task_key, task_stat in stats["task_stats"].items():
        if task_stat["total"] >= min_failures:
            fail_rate = 100 - task_stat["percent"]
            if fail_rate > 50:
                problematic.append(
                    {
                        "task": task_stat["task"],
                        "section": task_stat["section"],
                        "completed": task_stat["completed"],
                        "total": task_stat["total"],
                        "percent": task_stat["percent"],
                        "fail_rate": fail_rate,
                    }
                )

    problematic.sort(key=lambda x: x["fail_rate"], reverse=True)
    return problematic


def get_today_date_from_file() -> Optional[str]:
    return get_today_date_from_state()


def get_pending_tasks() -> Dict[str, List[str]]:
    today_status = load_today_status()
    morning_tasks, day_tasks, evening_tasks = load_tasks_config()

    pending: dict[str, list[str]] = {"morning": [], "day": [], "evening": []}

    for task in morning_tasks:
        if not today_status["morning"].get(task, False):
            pending["morning"].append(task)

    for task in day_tasks:
        if not today_status["day"].get(task, False):
            pending["day"].append(task)

    for task in evening_tasks:
        if not today_status["evening"].get(task, False):
            pending["evening"].append(task)

    return pending


def should_send_morning_reminder() -> bool:
    now_msk = get_current_time_msk()
    current_hour = now_msk.hour

    if 8 <= current_hour < 10:
        file_date = get_today_date_from_file()
        today_date = now_msk.strftime("%Y-%m-%d")

        if file_date == today_date:
            pending = get_pending_tasks()
            return len(pending["morning"]) > 0

    return False


def should_send_evening_reminder() -> bool:
    now_msk = get_current_time_msk()
    current_hour = now_msk.hour

    if 21 <= current_hour < 23:
        file_date = get_today_date_from_file()
        today_date = now_msk.strftime("%Y-%m-%d")

        if file_date == today_date:
            pending = get_pending_tasks()
            return len(pending["evening"]) > 0

    return False


def format_statistics_text(stats: Dict) -> str:
    from planning_bot.core.pdmsg import pdmsg, pdmsg_nl

    text = pdmsg_nl("auto_10748013ee", _p1=stats["days_analyzed"])
    text += pdmsg_nl(
        "auto_c2c1bb23fc",
        _p1=stats["morning_percent"],
        _p3=stats["total_morning_completed"],
        _p5=stats["total_morning_possible"],
    )
    text += pdmsg_nl(
        "auto_db93289bfb",
        _p1=stats["day_percent"],
        _p3=stats["total_day_completed"],
        _p5=stats["total_day_possible"],
    )
    text += pdmsg_nl(
        "auto_0579aaf570",
        _p1=stats["evening_percent"],
        _p3=stats["total_evening_completed"],
        _p5=stats["total_evening_possible"],
    )

    problematic = get_problematic_tasks(days=stats["days_analyzed"], min_failures=2)
    if problematic:
        text += pdmsg_nl("auto_c8396189f5")
        for task in problematic[:5]:
            if task["section"] == "morning":
                emoji = "🌅"
            elif task["section"] == "day":
                emoji = "☀️"
            else:
                emoji = "🌙"
            text += f"{emoji} {task['task']}: {task['percent']}% ({task['completed']}/{task['total']})\n"

    return text
