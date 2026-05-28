#!/usr/bin/env python3
"""
Ежедневное обслуживание 700_ (хабы, wikilinks, опционально reprocess) — см. config/vault_maintenance.yaml.

  python tools/vault_daily_maintenance.py
  python tools/vault_daily_maintenance.py --force
  python tools/vault_daily_maintenance.py --sync-dir "/path/to/.sync"

Вызов из obsidian_sync.sh: шаг 5b.2, с SYNC_STATE_DIR.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Agent в PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from knowledge_bot.services.vault_maintenance import run_daily_maintenance


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Игнорировать маркер «уже сегодня»")
    ap.add_argument(
        "--sync-dir",
        type=Path,
        help="Папка маркеров (.sync), по умолчанию $SYNC_STATE_DIR или vault/.sync",
    )
    ap.add_argument("--json", action="store_true", help="Вывод JSON (для логов)")
    args = ap.parse_args()
    # Строка в лог сразу (5b.2), пока длинный прогон не завершён — важен PYTHONUNBUFFERED в obsidian_sync.sh
    print("[vault_daily_maintenance] start", flush=True)
    out = run_daily_maintenance(sync_dir=args.sync_dir, force=args.force)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, default=str, indent=2))
    else:
        print("vault_daily_maintenance:", "ok" if out.get("ok", True) else "ERR", out)
    if out.get("skipped"):
        sys.exit(0)
    sys.exit(0 if out.get("ok", True) else 1)


if __name__ == "__main__":
    main()
