#!/usr/bin/env python3
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

"""
Выводит из логов действий события, попадающие в «неизвестно» на графике Активность_за_день
(задачи без приоритета: нет в данных события и не найдены на доске с тегом #приоритет/).
Запуск из корня vault: python3 800_Автоматизация/Agent/planning_bot/scripts/show_unknown_priority_events.py [--vault PATH]
"""

import argparse
import re
import sys
from pathlib import Path

from planning_bot.services.action_log_parser import collect_events_from_logs


def _discover_vault(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "100_Задачи").exists() and (p / "300_Дашборды").exists():
            return p
    return start.parents[3]


def _load_kanban_priority_index(vault: Path) -> tuple[dict[str, str], dict[str, str]]:
    kanban_path = vault / "100_Задачи" / "📋 Доска_Задач.md"
    if not kanban_path.exists():
        return {}, {}
    text = kanban_path.read_text(encoding="utf-8", errors="replace")
    prio_by_id: dict[str, str] = {}
    prio_by_title: dict[str, str] = {}
    task_pattern = r"- \[[ x]\] (.+?)(?=\n- \[|\n## |\n%%|$)"
    for m in re.finditer(task_pattern, text, re.DOTALL):
        task_text = m.group(1).strip()
        for sep in ("\n## ", "\n%%"):
            if sep in task_text:
                task_text = task_text.split(sep)[0].strip()
        title_line = task_text.splitlines()[0].strip() if task_text else ""
        title = title_line.strip()
        priority_match = re.search(r"#приоритет/(высокий|средний|низкий)", task_text)
        id_match = re.search(r"🆔 ID:\s*([a-f0-9-]{6,})", task_text, re.IGNORECASE)
        pr = priority_match.group(1).strip() if priority_match else ""
        tid = id_match.group(1).strip() if id_match else ""
        if not pr:
            continue
        if tid:
            prio_by_id[tid] = pr
        if title:
            prio_by_title[title] = pr
    return prio_by_id, prio_by_title


def _get_prio(d: dict, prio_by_id: dict, prio_by_title: dict) -> str:
    pr = (d.get("priority") or "").strip()
    if pr in ("высокий", "средний", "низкий"):
        return pr
    tid = d.get("task_id")
    if tid and str(tid) in prio_by_id:
        return prio_by_id[str(tid)]
    title = (d.get("title") or "").strip()
    if title and title in prio_by_title:
        return prio_by_title[title]
    return "неизвестно"


def main() -> None:
    p = argparse.ArgumentParser(description="События из логов с приоритетом «неизвестно»")
    p.add_argument("--vault", type=Path, default=None)
    args = p.parse_args()
    vault = Path(args.vault).resolve() if args.vault else _discover_vault(Path(__file__).resolve())
    action_logs_dir = vault / "300_Дашборды" / "Логи"
    if not action_logs_dir.is_dir():
        print(f"Папка логов не найдена: {action_logs_dir}", file=sys.stderr)
        sys.exit(1)
    events = collect_events_from_logs(action_logs_dir)
    prio_by_id, prio_by_title = _load_kanban_priority_index(vault)
    unknown = [
        e for e in events
        if e.get("type") in ("task_created", "task_moved", "task_completed")
        and _get_prio(e.get("data") or {}, prio_by_id, prio_by_title) == "неизвестно"
    ]
    if not unknown:
        print("Событий с приоритетом «неизвестно» нет.")
        return
    print(f"События «неизвестно» (всего {len(unknown)}):\n")
    for e in unknown:
        d = e.get("data") or {}
        ts = e.get("timestamp", "")
        typ = e.get("type", "")
        title = (d.get("title") or "").strip() or "(без названия)"
        tid = d.get("task_id") or ""
        print(f"  {ts}  {typ:16}  {tid or '(нет id)'}  {title[:60]}{'…' if len(title) > 60 else ''}")


if __name__ == "__main__":
    main()
