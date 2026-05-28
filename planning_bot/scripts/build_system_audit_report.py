#!/usr/bin/env python3
"""
Read-only сводка состояния «системы» Obsidian + planning: синк, логи, доска, графики.
Ничего в vault не меняет кроме перезаписи этого отчёта.

Выход по умолчанию: 300_Дашборды/Аудит_системы_отчет.md

Запуск (как в obsidian_sync):
  PYTHONPATH=... python3 scripts/build_system_audit_report.py --vault /path/to/vault
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path


def _discover_vault(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "100_Задачи").exists() and (p / "300_Дашборды").exists():
            return p
    return start.parents[3]


def _safe_read(path: Path, max_bytes: int = 4000) -> str:
    if not path.exists():
        return "(нет файла)"
    try:
        raw = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        return f"(ошибка чтения: {e})"
    if len(raw) > max_bytes:
        return raw[:max_bytes] + f"\n… обрезано ({len(raw)} символов всего)"
    return raw


def _mtime_iso(path: Path) -> str:
    if not path.exists():
        return "—"
    try:
        return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
    except OSError:
        return "?"


def main() -> None:
    p = argparse.ArgumentParser(description="Аудит системы (read-only, один .md отчёт)")
    p.add_argument("--vault", type=Path, default=None)
    p.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Файл отчёта (по умолчанию: vault/300_Дашборды/Аудит_системы_отчет.md)",
    )
    args = p.parse_args()

    vault = args.vault.resolve() if args.vault else _discover_vault(Path(__file__).resolve())
    dash = vault / "300_Дашборды"
    out = args.out or (dash / "Аудит_системы_отчет.md")
    if not out.is_absolute():
        out = vault / out
    out.parent.mkdir(parents=True, exist_ok=True)

    sync_dir = Path(os.environ.get("SYNC_STATE_DIR", vault / ".sync"))
    if not sync_dir.is_dir():
        sync_dir = vault / ".sync"

    lines: list[str] = [
        "# Аудит системы (Obsidian + planning)",
        "",
        f"Сгенерировано: **{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}** (локальное время машины, где запущен скрипт).",
        "",
        "Только чтение метаданных и подсчёты; задачи/заметки **не** изменяются.",
        "",
        "---",
        "",
        "## 1. Синхронизация и маркеры (`.sync/`)",
        "",
        f"Каталог состояния: `{sync_dir}`",
        "",
    ]

    markers = [
        "last_sync_ok.txt",
        "daily_charts_date.txt",
        "finance_dashboard_date.txt",
        "finance_dashboard_last_ok.txt",
    ]
    for name in markers:
        path = sync_dir / name
        lines.append(f"- **`{name}`** — mtime {_mtime_iso(path)}")
        if name == "last_sync_ok.txt":
            lines.append(f"  - содержимое: `{_safe_read(path, 500).strip()}`")
        elif path.exists():
            lines.append(f"  - содержимое: `{path.read_text(encoding='utf-8', errors='replace').strip()}`")
        lines.append("")

    health_log = sync_dir / "health.log"
    lines.append("### health.log (хвост)")
    lines.append("")
    lines.append("```")
    if health_log.exists():
        try:
            tail = health_log.read_text(encoding="utf-8", errors="replace").splitlines()[-40:]
            lines.append("\n".join(tail) if tail else "(пусто)")
        except OSError as e:
            lines.append(str(e))
    else:
        lines.append("(нет файла)")
    lines.append("```")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 2. Planning: доска и состояние канбана")
    lines.append("")

    kanban = vault / "100_Задачи" / "📋 Доска_Задач.md"
    lines.append(f"- **Доска:** `{kanban}` — {_mtime_iso(kanban)}, размер {kanban.stat().st_size if kanban.exists() else '—'} байт")

    ks = dash / "kanban_state.json"
    if ks.exists():
        try:
            data = json.loads(ks.read_text(encoding="utf-8"))
            n = len(data) if isinstance(data, dict) else 0
            lines.append(f"- **kanban_state.json** — записей о задачах: **{n}**, mtime {_mtime_iso(ks)}")
        except Exception as e:
            lines.append(f"- **kanban_state.json** — ошибка разбора: {e}")
    else:
        lines.append("- **kanban_state.json** — нет файла (нормально, если ещё не создавался)")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 3. Action-логи и события")
    lines.append("")

    agent = vault / "800_Автоматизация" / "Agent"
    sys.path.insert(0, str(agent))
    from planning_bot.services.action_log_parser import collect_events_from_logs

    logs_dir = dash / "Логи"
    if logs_dir.is_dir():
        md_logs = sorted(logs_dir.glob("📊 Логи_Действий_*.md"))
        lines.append(f"- Файлов логов: **{len(md_logs)}**")
        for f in md_logs[-6:]:
            lines.append(f"  - `{f.name}` — {_mtime_iso(f)}")
        try:
            ev = collect_events_from_logs(logs_dir)
            lines.append(f"- Событий всего (парсер): **{len(ev)}**")
        except Exception as e:
            lines.append(f"- Ошибка подсчёта событий: `{e}`")
    else:
        lines.append("- Каталог `300_Дашборды/Логи/` не найден")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 4. Дашборды: вспомогательные файлы")
    lines.append("")

    for rel in (
        "goals_task_mapping.json",
        "Графики/open_tasks_by_day_history.json",
    ):
        fp = dash / rel
        lines.append(f"- `{rel}` — {_mtime_iso(fp)}, размер {fp.stat().st_size if fp.exists() else '—'} байт")

    lines.append("")
    lines.append("### Графики (ключевые файлы)")
    lines.append("")
    gfx = dash / "Графики"
    watch = [
        "Активность_за_день.png",
        "Завершено_по_категориям_дни.png",
        "Открыто_по_категориям_дни.png",
    ]
    if gfx.is_dir():
        for w in watch:
            fp = gfx / w
            lines.append(f"- `{w}` — {_mtime_iso(fp)}")
    else:
        lines.append("- Папка `Графики/` не найдена")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## 5. Переменные окружения (только имена)")
    lines.append("")
    for key in ("VAULT_PATH", "LOCAL_VAULT", "SYNC_STATE_DIR", "PYTHONPATH"):
        v = os.environ.get(key)
        lines.append(f"- `{key}` — {'задана' if v else 'не задана'}")
    lines.append("")
    lines.append("_При проблемах смотри `planning_bot/logs/charts.log` (графики) и логи бота в `planning_bot/logs/`._")

    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Записано: {out}")


if __name__ == "__main__":
    main()
