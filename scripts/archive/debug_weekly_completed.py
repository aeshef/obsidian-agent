#!/usr/bin/env python3
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

"""
Отладка: сколько задач «выполнено за неделю» по логам. Использует общий парсер логов (action_log_parser).
"""

import argparse
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from planning_bot.services.action_log_parser import collect_events_from_logs, get_completion_events, is_completion_event


def _completion_events_to_legacy(events: list[dict]) -> list[dict]:
    """Формат как раньше: task_id, title, timestamp."""
    out = []
    for e in events:
        d = e.get("data") or {}
        out.append({
            "task_id": d.get("task_id"),
            "title": (d.get("title") or "").strip(),
            "timestamp": e["timestamp"],
        })
    return out


def _moved_events_in_range(events: list[dict], from_date: datetime, to_date: datetime) -> list[dict]:
    moved = [e for e in events if e.get("type") == "task_moved" and from_date <= e["dt"] <= to_date]
    return [
        {"timestamp": e["timestamp"], "title": (e.get("data") or {}).get("title") or "", "from": (e.get("data") or {}).get("from") or "", "to": (e.get("data") or {}).get("to") or ""}
        for e in moved
    ]


def main():
    parser = argparse.ArgumentParser(description="Отладка: выполнено за неделю по логам")
    parser.add_argument("--vault", type=Path, default=None, help="Корень Vault")
    parser.add_argument("--logs", type=Path, default=None, help="Папка с логами")
    parser.add_argument("--board", type=Path, default=None, help="Файл доски (только для справки)")
    args = parser.parse_args()

    if args.vault is not None:
        vault = args.vault.resolve()
        logs_dir = vault / "300_Дашборды" / "Логи"
        kanban_file = vault / "100_Задачи/📋 Доска_Задач.md"
    else:
        try:
            from planning_bot.core.config import ACTION_LOGS_DIR, KANBAN_FILE
            logs_dir = Path(ACTION_LOGS_DIR)
            kanban_file = Path(KANBAN_FILE)
        except Exception:
            vault = Path(__file__).resolve().parent.parent.parent.parent
            logs_dir = vault / "300_Дашборды" / "Логи"
            kanban_file = vault / "100_Задачи/📋 Доска_Задач.md"

    if args.logs is not None:
        logs_dir = args.logs.resolve()
    if args.board is not None:
        kanban_file = args.board.resolve()

    events = collect_events_from_logs(logs_dir)
    today = datetime.now()
    cur_week_start = today - timedelta(days=today.weekday())
    cur_week_end = cur_week_start + timedelta(days=6, hours=23, minutes=59, seconds=59)
    prev_week_end = cur_week_start - timedelta(seconds=1)
    prev_week_start = prev_week_end - timedelta(days=6)

    cur_week_events = [e for e in events if cur_week_start <= e["dt"] <= cur_week_end]
    prev_week_events = [e for e in events if prev_week_start <= e["dt"] <= prev_week_end]

    all_completion = get_completion_events(events, filter_batch=True, dedup_per_task=True)
    cur_completion = get_completion_events(cur_week_events, filter_batch=True, dedup_per_task=True)
    prev_completion = get_completion_events(prev_week_events, filter_batch=True, dedup_per_task=True)

    all_events = _completion_events_to_legacy(all_completion)
    cur_unique = _completion_events_to_legacy(cur_completion)
    prev_unique = _completion_events_to_legacy(prev_completion)

    print("=== Выполнено за неделю (только по логам) ===\n")
    print(f"Логи: {logs_dir}")
    print(f"Доска (для справки): {kanban_file}\n")

    print("В логах всего событий завершения (task_completed + task_moved→Сделано):", len(all_events))
    if all_events:
        print("  Примеры дат:", all_events[0].get("timestamp"), "...", all_events[-1].get("timestamp"))

    print("\nТекущая неделя (пн–вс):", cur_week_start.strftime("%Y-%m-%d"), "—", cur_week_end.strftime("%Y-%m-%d"))
    print("  Событий завершения:", len([e for e in cur_week_events if is_completion_event(e)]), "| после дедупа:", len(cur_unique))
    if cur_unique:
        for item in cur_unique[:5]:
            print("   ", item.get("timestamp"), "|", (item.get("title") or "")[:55])

    print("\nПрошлая неделя (пн–вс):", prev_week_start.strftime("%Y-%m-%d"), "—", prev_week_end.strftime("%Y-%m-%d"))
    print("  Событий завершения:", len([e for e in prev_week_events if is_completion_event(e)]), "| после дедупа (уникальных задач):", len(prev_unique))
    prev_by_day = Counter((e.get("timestamp", "")[:10] for e in prev_unique))
    if prev_by_day:
        print("  По дням (событий завершения):", dict(sorted(prev_by_day.items())))
    if prev_unique:
        print("  Примеры (первые 5):")
        for item in prev_unique[:5]:
            print("   ", item.get("timestamp"), "|", (item.get("title") or "")[:55])

    prev_moves = _moved_events_in_range(events, prev_week_start, prev_week_end)
    print("\nПеремещения за прошлую неделю (все task_moved):", len(prev_moves))
    if prev_moves:
        moves_by_day = Counter((m["timestamp"][:10] for m in prev_moves))
        print("  По дням:", dict(sorted(moves_by_day.items())))
        print("  Первые 15 (timestamp | title | from → to):")
        for m in prev_moves[:15]:
            print("   ", m["timestamp"], "|", (m["title"] or "")[:40], "|", m["from"], "→", m["to"])
        out_file = Path(__file__).resolve().parent.parent / "debug_moves_prev_week.txt"
        with open(out_file, "w", encoding="utf-8") as f:
            f.write(f"Неделя {prev_week_start.strftime('%Y-%m-%d')} — {prev_week_end.strftime('%Y-%m-%d')}\n")
            f.write(f"Всего перемещений: {len(prev_moves)}\n\n")
            for m in prev_moves:
                f.write(f"{m['timestamp']} | \"{m['title']}\" | {m['from']} → {m['to']}\n")
        print("  Полная цепочка записана в:", out_file)

    print("\n---")
    if cur_week_start.date() == today.date():
        print("Сегодня понедельник: в ревью в воскресенье использовалась бы «прошлая неделя» →", len(prev_unique), "уникальных задач.")
    else:
        print("В ревью в воскресенье используется «текущая неделя» →", len(cur_unique), "задач.")
    if kanban_file.exists():
        text = kanban_file.read_text(encoding="utf-8")
        total_done = len(re.findall(r'- \[x\] ', text))
        print("На доске всего выполненных пунктов:", total_done)
        if prev_unique and total_done:
            print("  (Если 172 за прошлую неделю верно, то до её начала было завершено", total_done - len(prev_unique), "задач. Проверь по цепочке выше.)")
    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
