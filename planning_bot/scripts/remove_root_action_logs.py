#!/usr/bin/env python3
"""
Удаление устаревших файлов логов из корня 300_Дашборды (не из Логи/).

Почему файл появляется в корне:
- В текущем коде все пишут только в ACTION_LOGS_DIR = 300_Дашборды/Логи/ (action_logger, vault_maintenance, bot).
- Файл в корне — остаток старой структуры. Он снова появляется, потому что при push 300_ мы отправляем
  всё из локальной папки; если локально лежит 📊 Логи_Действий_*.md в корне 300_, он уезжает на сервер.
  В obsidian_sync.sh при push исключён корневой /📊 Логи_Действий_*.md — после удаления он не будет переотправлен.

Запуск:
  Из корня vault: python 800_Автоматизация/Agent/planning_bot/scripts/remove_root_action_logs.py [--vault PATH]
  Или из planning_bot: python scripts/remove_root_action_logs.py

После запуска выведется команда для удаления на сервере (если есть).
"""
import argparse
import sys
from pathlib import Path

LOG_PREFIX = "📊 Логи_Действий_"


def main():
    ap = argparse.ArgumentParser(description="Удалить файлы 📊 Логи_Действий_*.md из корня 300_Дашборды (не из Логи/)")
    ap.add_argument("--vault", type=Path, default=None, help="Путь к vault")
    ap.add_argument("--dry-run", action="store_true", help="Только показать, что будет удалено")
    args = ap.parse_args()

    if args.vault:
        dash = Path(args.vault) / "300_Дашборды"
    else:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
        from planning_bot.core.config import LOGS_DIR
        dash = LOGS_DIR

    if not dash.is_dir():
        print(f"Каталог не найден: {dash}", flush=True)
        return 1

    # Только файлы в корне 300_Дашборды (не в подкаталогах)
    removed = []
    for f in dash.glob(f"{LOG_PREFIX}*.md"):
        if f.parent != dash:
            continue
        if args.dry_run:
            print(f"  [dry-run] удалить: {f}", flush=True)
        else:
            f.unlink()
            print(f"  удалён: {f}", flush=True)
        removed.append(f.name)

    if not removed:
        print("В корне 300_Дашборды файлов логов не найдено.", flush=True)
    elif not args.dry_run:
        print(f"Удалено файлов: {len(removed)}", flush=True)
        print("На сервере выполни один раз (подставь свой vault на сервере при необходимости):", flush=True)
        print('  ssh example-server "rm -f /root/obsidian-vault/300_Дашборды/📊 Логи_Действий_*.md"', flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
