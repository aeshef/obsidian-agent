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


def _build_maintenance_section(vault: Path) -> str:
    """Собирает секцию состояния ежедневного обслуживания."""
    import yaml, datetime

    lines = ["## 3. Ежедневное обслуживание (vault_daily_maintenance)", ""]

    # Статус хабов
    hubs_dir = vault / "700_База_Данных" / "_Хабы"
    if hubs_dir.exists():
        hubs = sorted(hubs_dir.glob("*.md"))
        lines.append(f"**Хабы** (`700_База_Данных/_Хабы/`): {len(hubs)} файлов")
        for h in hubs:
            mtime = datetime.datetime.fromtimestamp(h.stat().st_mtime).strftime("%Y-%m-%d")
            try:
                text = h.read_text(encoding="utf-8", errors="ignore")
                link_count = text.count("[[")
                lines.append(f"  - `{h.name}` — {link_count} ссылок (обновлён {mtime})")
            except Exception:
                lines.append(f"  - `{h.name}` (обновлён {mtime})")
    else:
        lines.append("**Хабы**: папка `_Хабы/` ещё не создана (запусти `sync_hubs.py --apply`)")

    lines.append("")

    # Tag ontology mappings count
    tag_cfg_path = Path(__file__).resolve().parent.parent / "config" / "tag_ontology.yaml"
    if tag_cfg_path.exists():
        try:
            tcfg = yaml.safe_load(tag_cfg_path.read_text(encoding="utf-8")) or {}
            mappings = tcfg.get("mappings", {}) or {}
            lines.append(f"**Онтология тегов**: {len(mappings)} активных маппингов в `config/tag_ontology.yaml`")
        except Exception:
            lines.append("**Онтология тегов**: ошибка чтения конфига")
    else:
        lines.append("**Онтология тегов**: конфиг не найден")

    lines.append("")

    # Marker file (last run date)
    sync_dir = vault / ".sync"
    marker = sync_dir / "daily_vault_write_maintenance_date.txt"
    if marker.exists():
        last_run = marker.read_text(encoding="utf-8").strip()
        lines.append(f"**Последний запуск обслуживания**: `{last_run}`")
    else:
        lines.append("**Последний запуск обслуживания**: ещё не запускалось (маркер не найден)")

    lines.append("")

    # Notes with bad titles (quick count)
    bad_stems = {"Без_названия", "Субтитры", "Редактор_субтитров", "Динамичная_музыка",
                 "Позитивная_музыка", "Спокойная_музыка", "OCR_текст", "YouTube"}
    bad_notes = []
    target_dirs = [vault / "700_База_Данных" / d for d in ["Видео", "Знания", "Песни", "Ссылки"]]
    for d in target_dirs:
        if d.exists():
            for f in d.glob("*.md"):
                for stem in bad_stems:
                    if f.stem.startswith(stem):
                        bad_notes.append(f.relative_to(vault))
                        break
    if bad_notes:
        lines.append(f"**Заметки для reprocess** (generic имена): {len(bad_notes)}")
        for p in sorted(bad_notes)[:8]:
            lines.append(f"  - `{p}`")
        if len(bad_notes) > 8:
            lines.append(f"  - … и ещё {len(bad_notes) - 8}")
    else:
        lines.append("**Заметки для reprocess**: не найдено (все имена нормальные)")

    lines.append("")
    return "\n".join(lines)


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

    import datetime
    maintenance_section = _build_maintenance_section(vault)

    report_lines = [
        "# Аудит хранилища 700_База_Данных",
        "",
        f"Обновлён: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}",
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
        "---",
        "",
        maintenance_section,
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
