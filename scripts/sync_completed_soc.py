#!/usr/bin/env python3
"""
Source of Truth по выполненным задачам: JSON-лог, который строится по доске задач.

- Читает колонку «✅ Сделано» с доски.
- Добавляет в SoC только задачи, которых ещё не было (completed_at = дата запуска).
- При первом запуске (файл пустой) все текущие в «Сделано» записываются с completed_at = null,
  чтобы не создавать всплеск на графике — в график попадают только новые завершения после этого.
- Запускать с адекватным интервалом (раз в день или при vault_maintenance).

Файл: 300_Дашборды/Графики/completed_tasks_soc.json
"""

import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Optional


def _get_task_id_from_text(task_text: str) -> Optional[str]:
    id_match = re.search(r'🆔 ID: ([a-f0-9-]+)', task_text)
    if id_match:
        return id_match.group(1)
    date_match = re.search(r'📅 Создано: (\d{4}-\d{2}-\d{2})', task_text)
    category_match = re.search(r'#цель/([^\s#]+)', task_text)
    priority_match = re.search(r'#приоритет/(высокий|средний|низкий)', task_text)
    task_name = re.sub(r'\s*#цель/[^\s#]+.*', '', task_text).strip()
    task_name = re.sub(r'\s*#приоритет/[^\s#]+.*', '', task_name).strip()
    task_name = re.sub(r'\s*#дедлайн/[^\s#]+.*', '', task_name).strip()
    task_name = re.sub(r'\s*📅 Создано:.*', '', task_name).strip()
    task_name = re.sub(r'\s*🆔 ID:.*', '', task_name).strip()
    task_name = task_name.replace('\\$', '$').replace('\\\\', '\\')
    hash_parts = []
    if date_match:
        hash_parts.append(date_match.group(1))
    if category_match:
        hash_parts.append(category_match.group(1))
    if priority_match:
        hash_parts.append(priority_match.group(1))
    hash_parts.append(task_name[:50])
    if hash_parts:
        return hashlib.md5('|'.join(hash_parts).encode('utf-8')).hexdigest()[:8]
    return None


def _get_category_from_text(task_text: str) -> Optional[str]:
    """Категория из тега #цель/...; если тега нет — None (на графике такие задачи не показываются)."""
    m = re.search(r'#цель/([^\s#]+)', task_text)
    return m.group(1) if m else None


def _read_done_tasks_from_board(kanban_path: Path) -> list[dict]:
    """Список { task_id, category } для задач в колонке «✅ Сделано»."""
    if not kanban_path.exists():
        return []
    content = kanban_path.read_text(encoding="utf-8")
    done_match = re.search(
        r'##\s*✅\s*Сделано\s*\n\n(.+?)(?=\n##\s|\n%%|$)',
        content,
        re.DOTALL,
    )
    if not done_match:
        return []
    section = done_match.group(1)
    tasks = []
    for m in re.finditer(r'- \[x\]\s+(.+?)(?=\n- \[|$)', section, re.DOTALL):
        task_text = m.group(1).strip()
        task_id = _get_task_id_from_text(task_text)
        if not task_id:
            continue
        category = _get_category_from_text(task_text)
        tasks.append({"task_id": task_id, "category": category})  # category None = нет #цель/
    return tasks


def sync_completed_soc(
    kanban_path: Path,
    soc_path: Path,
    today: Optional[str] = None,
) -> int:
    """
    Синхронизирует SoC с доской. Возвращает число добавленных записей с ненулевой датой.
    today — YYYY-MM-DD (по умолчанию сегодня).
    """
    if today is None:
        today = datetime.now().strftime("%Y-%m-%d")
    done_tasks = _read_done_tasks_from_board(kanban_path)
    if not done_tasks:
        return 0

    if soc_path.exists():
        try:
            data = json.loads(soc_path.read_text(encoding="utf-8"))
        except Exception:
            data = {"entries": [], "updated": None}
    else:
        data = {"entries": [], "updated": None}

    existing_ids = {e["task_id"] for e in data["entries"]}
    first_run = len(data["entries"]) == 0
    added = 0
    for t in done_tasks:
        if t["task_id"] in existing_ids:
            continue
        # Первый запуск: все текущие «Сделано» — без даты, чтобы не всплеск на графике
        data["entries"].append({
            "task_id": t["task_id"],
            "category": t["category"],
            "completed_at": None if first_run else today,
        })
        existing_ids.add(t["task_id"])
        if not first_run:
            added += 1

    data["updated"] = datetime.now().isoformat()
    soc_path.parent.mkdir(parents=True, exist_ok=True)
    soc_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return added


def main():
    import argparse
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    p = argparse.ArgumentParser(description="Синк SoC по выполненным задачам с доски")
    p.add_argument("--vault", type=Path, default=None)
    p.add_argument("--soc", type=Path, default=None)
    args = p.parse_args()

    if args.vault is not None:
        vault = args.vault.resolve()
        kanban_path = vault / "100_Задачи/📋 Доска_Задач.md"
        soc_path = args.soc or (vault / "300_Дашборды/Графики/completed_tasks_soc.json")
    else:
        try:
            from planning_bot.core.config import KANBAN_FILE, COMPLETED_SOC_FILE
            kanban_path = Path(KANBAN_FILE)
            soc_path = args.soc or Path(COMPLETED_SOC_FILE)
        except Exception:
            vault = Path(__file__).resolve().parent.parent.parent.parent
            kanban_path = vault / "100_Задачи/📋 Доска_Задач.md"
            soc_path = args.soc or (vault / "300_Дашборды/Графики/completed_tasks_soc.json")

    n = sync_completed_soc(kanban_path, soc_path)
    print(f"SoC: {soc_path} (добавлено с датой: {n})")


if __name__ == "__main__":
    main()
