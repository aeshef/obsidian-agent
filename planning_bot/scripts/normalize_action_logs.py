#!/usr/bin/env python3
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

"""
Нормализация полей to/from в логах действий: если в них попал многострочный текст
(баг get_kanban_state с re.DOTALL), оставляем только первую строку — имя колонки.

После нормализации нужно один раз отправить исправленные логи на сервер (--push-to-server),
чтобы при следующем синке серверная версия не перезаписала локальную: ground truth будет на сервере.

Запуск из корня vault:
  python3 .../normalize_action_logs.py [--vault PATH] [--month 2026-03] [--dry-run] [--push-to-server]
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

LOG_PREFIX = "📊 Логи_Действий_"
MONTH_NAMES = ("", "January", "February", "March", "April", "May", "June",
               "July", "August", "September", "October", "November", "December")

from planning_bot.services.action_log_parser import parse_log_content


def first_line_only(s: str) -> str:
    """Оставить только первую строку (имя колонки)."""
    if not s or "\n" not in s:
        return s
    return s.split("\n")[0].strip()


def normalize_data(data: dict) -> dict:
    """Исправить to/from в данных события."""
    if not isinstance(data, dict):
        return data
    out = dict(data)
    if "to" in out and isinstance(out["to"], str):
        out["to"] = first_line_only(out["to"])
    if "from" in out and isinstance(out["from"], str):
        out["from"] = first_line_only(out["from"])
    return out


def write_log_file(path: Path, events: list, year_month: str) -> None:
    """Записать файл в формате action_logger."""
    if not events:
        return
    y, m = year_month.split("-")
    month_title = f"{MONTH_NAMES[int(m)]} {y}"
    lines = [f"# Логи действий {month_title}\n\n"]
    for e in events:
        ts = e["timestamp"]
        typ = e.get("type", "")
        data = e.get("data") or {}
        data_json = json.dumps(data, ensure_ascii=False, indent=2)
        lines.append(f"## {ts}\n\n")
        lines.append(f"**Тип:** {typ}\n\n")
        lines.append("**Данные:**\n```json\n")
        lines.append(data_json)
        lines.append("\n```\n\n---\n\n")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(lines), encoding="utf-8")


def main():
    ap = argparse.ArgumentParser(description="Нормализовать to/from в логах (оставить только имя колонки)")
    ap.add_argument("--vault", type=Path, default=None)
    ap.add_argument("--month", type=str, default=None, help="Например 2026-03; иначе все файлы в Логи/")
    ap.add_argument("--dry-run", action="store_true", help="Только показать, что будет исправлено")
    ap.add_argument("--push-to-server", action="store_true", help="После нормализации отправить Логи/ на сервер (ground truth)")
    args = ap.parse_args()

    if args.vault:
        logs_dir = Path(args.vault) / "300_Дашборды" / "Логи"
    else:
        from planning_bot.core.config import ACTION_LOGS_DIR
        logs_dir = Path(ACTION_LOGS_DIR)

    if not logs_dir.is_dir():
        print(f"Каталог не найден: {logs_dir}", flush=True)
        return 1

    if args.month:
        files = [logs_dir / f"{LOG_PREFIX}{args.month}.md"]
        files = [f for f in files if f.exists()]
    else:
        files = sorted(logs_dir.glob(f"{LOG_PREFIX}*.md"))

    if not files:
        print("Нет файлов логов.", flush=True)
        return 0

    fixed_count = 0
    for path in files:
        content = path.read_text(encoding="utf-8")
        events = parse_log_content(content)
        if not events:
            continue
        year_month = path.stem.replace(LOG_PREFIX, "")
        if not year_month:
            continue
        changed = 0
        for e in events:
            data = e.get("data") or {}
            if not isinstance(data, dict):
                continue
            new_data = normalize_data(data)
            if new_data != data:
                changed += 1
            e["data"] = new_data
        if changed:
            fixed_count += changed
            if args.dry_run:
                print(f"  [dry-run] {path.name}: исправить {changed} записей", flush=True)
            else:
                write_log_file(path, events, year_month)
                print(f"  {path.name}: исправлено записей {changed}", flush=True)

    if fixed_count and not args.dry_run:
        print(f"Итого исправлено записей: {fixed_count}", flush=True)
    elif fixed_count and args.dry_run:
        print(f"Будет исправлено записей: {fixed_count}. Запусти без --dry-run.", flush=True)
    elif not fixed_count and not args.dry_run:
        print("Нормализация не потребовалась (to/from уже однострочные).", flush=True)

    if args.push_to_server and not args.dry_run and logs_dir.is_dir():
        server = os.environ["SERVER"]
        server_vault = os.environ.get("SERVER_VAULT", "/opt/obsidian-vault")
        rsh = os.environ.get("RSYNC_RSH", "ssh -o UseKeychain=yes -o BatchMode=yes")
        src = str(logs_dir.resolve()).rstrip("/") + "/"
        dst = f"{server}:{server_vault}/300_Дашборды/Логи/"
        cmd = ["rsync", "-avz", "-e", rsh, src, dst]
        print(f"Отправка логов на сервер: rsync ... {src} -> {dst}", flush=True)
        r = subprocess.run(cmd)
        if r.returncode != 0:
            print("Ошибка rsync (проверь SSH и путь на сервере).", flush=True)
            return 1
        print("Логи отправлены на сервер; при следующем синке подтянется уже исправленная версия.", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
