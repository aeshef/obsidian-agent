from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Tuple

from planning_bot.app.ui import pmsg
from planning_bot.services.routines_config import (
    SECTION_ORDER,
    section_config_header,
    section_history_label,
)
from planning_bot.services.routines_lock import routines_transaction
from shared.routines_paths import (
    routines_config_path,
    routines_history_path,
    routines_today_json_path,
    routines_today_legacy_path,
)
from shared.tz import get_tz

msk_tz = get_tz()


def _empty_status() -> Dict[str, Dict[str, bool]]:
    return {"morning": {}, "day": {}, "evening": {}}


def load_tasks_config() -> Tuple[List[str], List[str], List[str]]:
    path = routines_config_path()
    if not path.is_file():
        return [], [], []

    content = path.read_text(encoding="utf-8")
    lines = content.split("\n")

    morning_tasks: list[str] = []
    day_tasks: list[str] = []
    evening_tasks: list[str] = []
    current_section: str | None = None

    for line in lines:
        for section in SECTION_ORDER:
            if section_config_header(section) in line:
                current_section = section
                break
        else:
            if line.strip().startswith("- ") and current_section:
                task = line.strip()[2:].strip()
                if current_section == "morning":
                    morning_tasks.append(task)
                elif current_section == "day":
                    day_tasks.append(task)
                else:
                    evening_tasks.append(task)

    return morning_tasks, day_tasks, evening_tasks


def _parse_legacy_today_md(content: str) -> tuple[str, Dict[str, Dict[str, bool]]]:
    status = _empty_status()
    date_match = re.search(r"\*\*Дата:\*\*\s*(\d{4}-\d{2}-\d{2})", content)
    if not date_match:
        date_match = re.search(r"\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})", content)
    day = date_match.group(1) if date_match else ""
    current_section: str | None = None
    for line in content.split("\n"):
        for section in SECTION_ORDER:
            if section_config_header(section) in line:
                current_section = section
                break
        else:
            if current_section and line.strip().startswith("- ["):
                match = re.match(r"-\s*\[([ x])\]\s*(.+)", line.strip())
                if match:
                    status[current_section][match.group(2).strip()] = match.group(1) == "x"
    return day, status


def _read_today_payload() -> dict:
    json_path = routines_today_json_path()
    if json_path.is_file():
        try:
            raw = json.loads(json_path.read_text(encoding="utf-8"))
            if isinstance(raw, dict):
                return raw
        except json.JSONDecodeError:
            pass
    legacy = routines_today_legacy_path()
    if legacy.is_file():
        day, status = _parse_legacy_today_md(legacy.read_text(encoding="utf-8"))
        return {"date": day, "status": status}
    return {"date": "", "status": _empty_status()}


def _write_today_payload(day: str, status: Dict[str, Dict[str, bool]]) -> None:
    path = routines_today_json_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "date": day,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
    }
    with routines_transaction(path):
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_today_status() -> Dict[str, Dict[str, bool]]:
    payload = _read_today_payload()
    raw = payload.get("status")
    if not isinstance(raw, dict):
        return _empty_status()
    out = _empty_status()
    for section in SECTION_ORDER:
        section_data = raw.get(section)
        if isinstance(section_data, dict):
            out[section] = {str(k): bool(v) for k, v in section_data.items()}
    return out


def get_today_date() -> str:
    now_utc = datetime.now(timezone.utc)
    now_msk = now_utc.astimezone(msk_tz)
    return now_msk.strftime("%Y-%m-%d")


def get_today_date_from_state() -> str | None:
    day = str(_read_today_payload().get("date") or "").strip()
    return day or None


def format_status_for_history(
    morning_tasks_config: List[str],
    day_tasks_config: List[str],
    evening_tasks_config: List[str],
    today_status: Dict[str, Dict[str, bool]],
    date_to_save: str | None = None,
) -> str:
    lines: list[str] = []
    if date_to_save:
        date_str = date_to_save
    else:
        now_utc = datetime.now(timezone.utc)
        now_msk = now_utc.astimezone(msk_tz)
        yesterday_msk = now_msk - timedelta(days=1)
        date_str = yesterday_msk.strftime("%Y-%m-%d")

    lines.append(f"## {date_str}")
    lines.append("")
    lines.append(section_history_label("morning"))
    for task in morning_tasks_config:
        checked = today_status["morning"].get(task, False)
        lines.append(f"- {'✅' if checked else '⬜'} {task}")
    lines.append("")
    lines.append(section_history_label("day"))
    for task in day_tasks_config:
        checked = today_status["day"].get(task, False)
        lines.append(f"- {'✅' if checked else '⬜'} {task}")
    lines.append("")
    lines.append(section_history_label("evening"))
    for task in evening_tasks_config:
        checked = today_status["evening"].get(task, False)
        lines.append(f"- {'✅' if checked else '⬜'} {task}")
    lines.append("")
    lines.append("---")
    lines.append("")
    return "\n".join(lines)


def reset_today_state(
    morning_tasks: List[str],
    day_tasks: List[str],
    evening_tasks: List[str],
) -> None:
    status = _empty_status()
    for task in morning_tasks:
        status["morning"][task] = False
    for task in day_tasks:
        status["day"][task] = False
    for task in evening_tasks:
        status["evening"][task] = False
    _write_today_payload(get_today_date(), status)


def append_to_history(history_entry: str) -> None:
    path = routines_history_path()
    if path.is_file():
        current_content = path.read_text(encoding="utf-8")
        header_end = current_content.find("---")
        if header_end != -1:
            header = current_content[:header_end + 3]
            rest = current_content[header_end + 3:].lstrip()
            new_content = header + "\n\n" + history_entry + rest
        else:
            new_content = current_content + "\n\n" + history_entry
    else:
        header = pmsg("routines_history_header")
        new_content = f"{header}\n\n{history_entry}"
    path.write_text(new_content, encoding="utf-8")


def set_task_done(section: str, task: str, done: bool) -> bool:
    if section not in SECTION_ORDER or not task:
        return False
    check_and_update()
    status = load_today_status()
    if section not in status:
        return False
    if task not in status.get(section, {}):
        morning, day_tasks, evening = load_tasks_config()
        pools = {"morning": morning, "day": day_tasks, "evening": evening}
        if task not in pools.get(section, []):
            return False
        status[section][task] = done
    else:
        status[section][task] = done
    _write_today_payload(get_today_date_from_state() or get_today_date(), status)
    return True


def _sync_status_with_config(
    morning_tasks_config: List[str],
    day_tasks_config: List[str],
    evening_tasks_config: List[str],
    today_status: Dict[str, Dict[str, bool]],
) -> Dict[str, Dict[str, bool]]:
    out = _empty_status()
    for task in morning_tasks_config:
        out["morning"][task] = today_status["morning"].get(task, False)
    for task in day_tasks_config:
        out["day"][task] = today_status["day"].get(task, False)
    for task in evening_tasks_config:
        out["evening"][task] = today_status["evening"].get(task, False)
    return out


def check_and_update() -> None:
    from planning_bot.services.routines_layout import ensure_routines_layout

    ensure_routines_layout(scaffold_stats=False)

    morning_tasks_config, day_tasks_config, evening_tasks_config = load_tasks_config()
    if not morning_tasks_config and not day_tasks_config and not evening_tasks_config:
        return

    today_status = load_today_status()
    current_date = get_today_date()
    state_date = get_today_date_from_state()

    if state_date and state_date < current_date:
        history_entry = format_status_for_history(
            morning_tasks_config,
            day_tasks_config,
            evening_tasks_config,
            today_status,
            state_date,
        )
        append_to_history(history_entry)
        reset_today_state(morning_tasks_config, day_tasks_config, evening_tasks_config)
        return

    if not state_date:
        reset_today_state(morning_tasks_config, day_tasks_config, evening_tasks_config)
        return

    if state_date == current_date:
        synced = _sync_status_with_config(
            morning_tasks_config, day_tasks_config, evening_tasks_config, today_status
        )
        if synced != today_status:
            _write_today_payload(current_date, synced)
        return

    synced = _sync_status_with_config(
        morning_tasks_config, day_tasks_config, evening_tasks_config, today_status
    )
    _write_today_payload(current_date, synced)


if __name__ == "__main__":
    from planning_bot.services.routines_layout import ensure_routines_layout

    ensure_routines_layout()
    check_and_update()
