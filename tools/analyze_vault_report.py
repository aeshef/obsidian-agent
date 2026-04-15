#!/usr/bin/env python3
"""
Запускает оба анализа (теги + дубли) и при необходимости пишет сводный отчёт в файл.
Хранилище не меняет — только чтение. Отчёт можно писать в 300_Дашборды или в папку скриптов.

  python analyze_vault_report.py
  python analyze_vault_report.py --out "300_Дашборды/Аудит_хранилища_отчет.md"
  PYTHONPATH=../.. python tools/analyze_vault_report.py --vault /path/to/vault --out ...
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def _vault_root(args: argparse.Namespace) -> Path:
    if args.vault:
        return Path(args.vault).expanduser().resolve()
    from knowledge_bot.core.config import load_config

    return load_config().vault_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Сводный отчёт по тегам и дублям (read-only)")
    ap.add_argument(
        "--vault",
        type=str,
        default="",
        help="Корень Obsidian vault (как VAULT_PATH). Если не задан — из окружения/конфига.",
    )
    ap.add_argument("--out", "-o", type=str, default="", help="Путь к .md файлу отчёта (относительно vault или абсолютный)")
    args = ap.parse_args()

    vault = _vault_root(args)
    child_env = {**os.environ, "VAULT_PATH": str(vault)}

    # Запускаем оба скрипта и собираем вывод
    tags_out = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "analyze_vault_tags.py")],
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
        timeout=600,
        env=child_env,
    )
    dups_out = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "analyze_vault_duplicates.py")],
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
        timeout=600,
        env=child_env,
    )

    report_lines = [
        "# Аудит хранилища 700_База_Данных",
        "",
        "Скрипты: `analyze_vault_tags.py`, `analyze_vault_duplicates.py`. Только чтение.",
        "",
        "---",
        "",
        "## 1. Теги",
        "",
        "```",
        tags_out.stdout if tags_out.returncode == 0 else tags_out.stderr or "Ошибка",
        "```",
        "",
        "---",
        "",
        "## 2. Дубли (_1, _2, _3)",
        "",
        "```",
        dups_out.stdout if dups_out.returncode == 0 else dups_out.stderr or "Ошибка",
        "```",
        "",
    ]

    report_text = "\n".join(report_lines)

    if args.out:
        out_path = Path(args.out)
        if not out_path.is_absolute():
            out_path = vault / args.out
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(report_text, encoding="utf-8")
        print(f"Отчёт записан: {out_path}")
    else:
        print(report_text)


if __name__ == "__main__":
    main()
