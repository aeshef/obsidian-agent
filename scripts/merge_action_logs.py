#!/usr/bin/env python3
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

"""
Слияние логов действий из двух мест: корень 300_Дашборды и 300_Дашборды/Логи.
Используется после расхождения синка (локальные правки + события с сервера через бота).
Объединяет события по месяцам, дедупликация по (timestamp, type, data).
Результат пишется в 300_Дашборды/Логи/.
"""
import argparse
import json
from pathlib import Path

# Парсер — из корня planning_bot
import sys
from planning_bot.services.action_log_parser import parse_log_content

LOG_PREFIX = "📊 Логи_Действий_"
MONTH_NAMES = ("", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December")


def event_key(e: dict) -> tuple:
    """Ключ для дедупликации: одинаковые события дают один ключ."""
    data = e.get("data") or {}
    try:
        data_str = json.dumps(data, sort_keys=True, ensure_ascii=False)
    except Exception:
        data_str = str(data)
    return (e["timestamp"], e.get("type", "").strip(), data_str)


def write_log_file(path: Path, events: list, year_month: str) -> None:
    """Пишет файл лога в формате action_logger (заголовок + блоки ## ts, Тип, Данные)."""
    if not events:
        return
    # Заголовок: # Логи действий {Month YYYY}
    y, m = year_month.split("-")
    month_title = f"{MONTH_NAMES[int(m)]} {y}"
    lines = [f"# Логи действий {month_title}\n\n"]
    for e in events:
        ts = e["timestamp"]
        typ = e.get("type", "")
        data = e.get("data") or {}
        try:
            data_json = json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            data_json = "{}"
        lines.append(f"## {ts}\n\n")
        lines.append(f"**Тип:** {typ}\n\n")
        lines.append("**Данные:**\n```json\n")
        lines.append(data_json)
        lines.append("\n```\n\n---\n\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def merge_month(dash: Path, year_month: str, dry_run: bool = False) -> tuple[int, int]:
    """
    Объединяет логи за year_month из корня 300_Дашборды и из Логи/.
    Возвращает (число событий до слияния из обоих, число после дедупа).
    """
    name = f"{LOG_PREFIX}{year_month}.md"
    root_file = dash / name
    logs_dir = dash / "Логи"
    out_file = logs_dir / name

    events_from_root = []
    if root_file.exists():
        try:
            events_from_root = parse_log_content(root_file.read_text(encoding="utf-8"))
        except Exception as ex:
            print(f"  ⚠ Не удалось прочитать {root_file}: {ex}", flush=True)

    events_from_logs = []
    if out_file.exists():
        try:
            events_from_logs = parse_log_content(out_file.read_text(encoding="utf-8"))
        except Exception as ex:
            print(f"  ⚠ Не удалось прочитать {out_file}: {ex}", flush=True)

    all_events = events_from_root + events_from_logs
    total = len(all_events)
    if not all_events:
        return 0, 0

    # Дедуп по ключу, сохраняем порядок по времени (первое вхождение остаётся)
    seen = set()
    merged = []
    for e in sorted(all_events, key=lambda x: x["dt"]):
        k = event_key(e)
        if k in seen:
            continue
        seen.add(k)
        merged.append(e)

    if dry_run:
        print(f"  {year_month}: было {total} записей, после слияния {len(merged)}", flush=True)
        return total, len(merged)

    write_log_file(out_file, merged, year_month)
    if root_file.exists():
        root_file.unlink()
        print(f"  {year_month}: объединено {total} → {len(merged)} записей → {out_file}; удалён устаревший файл в корне 300_", flush=True)
    else:
        print(f"  {year_month}: объединено {total} → {len(merged)} записей → {out_file}", flush=True)
    return total, len(merged)


def main():
    ap = argparse.ArgumentParser(description="Слияние логов действий из корня 300_Дашборды и Логи/")
    ap.add_argument("--vault", type=Path, default=None, help="Путь к vault (по умолчанию из config)")
    ap.add_argument("--month", type=str, default=None, help="Год-месяц, например 2026-03; иначе все найденные")
    ap.add_argument("--dry-run", action="store_true", help="Только показать, что будет сделано")
    args = ap.parse_args()

    if args.vault:
        dash = Path(args.vault) / "300_Дашборды"
    else:
        from planning_bot.core.config import LOGS_DIR
        dash = LOGS_DIR  # уже 300_Дашборды

    if not dash.is_dir():
        print(f"Каталог не найден: {dash}", flush=True)
        return 1

    logs_dir = dash / "Логи"
    if args.month:
        months = [args.month]
    else:
        # Все месяцы: по файлам в Логи/ и в корне 300_Дашборды
        names = set()
        for d in (logs_dir, dash):
            if not d.exists() or not d.is_dir():
                continue
            for f in d.glob(f"{LOG_PREFIX}*.md"):
                stem = f.stem  # "📊 Логи_Действий_2026-03" → 2026-03
                if stem.startswith(LOG_PREFIX):
                    names.add(stem[len(LOG_PREFIX):])
        months = sorted(names) if names else []

    if not months:
        print("Нет файлов логов для слияния.", flush=True)
        return 0

    total_before, total_after = 0, 0
    for ym in months:
        a, b = merge_month(dash, ym, dry_run=args.dry_run)
        total_before += a
        total_after += b

    if not args.dry_run and total_after:
        print(f"Итого: записей до слияния {total_before}, после дедупа {total_after}", flush=True)
    return 0


if __name__ == "__main__":
    exit(main())
