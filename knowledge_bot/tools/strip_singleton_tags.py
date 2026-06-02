#!/usr/bin/env python3
"""
Удаляет из заметок 700_База_Данных теги, которые встречаются только в одной заметке (count=1).
Так уменьшается шум в графе от одноразовых тегов.

По умолчанию — dry-run (только печать, без изменений).
  python strip_singleton_tags.py
  python strip_singleton_tags.py --apply   # реально изменить файлы

Запускать после первой ревизии (strip_legacy, apply_duplicates, rebuild inventory).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from knowledge_bot.core.config import load_config
from knowledge_bot.services.tags_inventory import scan_all_notes
from shared.vault_layout import knowledge_subdir


def main() -> None:
    ap = argparse.ArgumentParser(description="Удалить из заметок теги с 1 заметкой (singleton)")
    ap.add_argument("--apply", action="store_true", help="Реально изменить файлы (иначе dry-run)")
    args = ap.parse_args()

    cfg = load_config()
    kd = knowledge_subdir()
    db_root = cfg.vault_path / kd
    if not db_root.exists():
        print(f"{kd} не найден", file=sys.stderr)
        sys.exit(1)

    inv = scan_all_notes(cfg.vault_path)
    tags_data = inv.get("tags", {})
    singleton_tags = {tag for tag, info in tags_data.items() if info.get("count", 0) == 1}
    if not singleton_tags:
        print("Нет тегов с 1 заметкой. Нечего удалять.")
        return

    print(f"Тегов с 1 заметкой: {len(singleton_tags)}")
    if not args.apply:
        print("=== DRY-RUN (запустите с --apply для применения) ===\n")

    modified = 0
    for path in sorted(db_root.rglob("*.md")):
        if "Export" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"  skip read {path}: {e}", file=sys.stderr)
            continue
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
        if not match:
            continue
        fm_str, body = match.group(1), match.group(2)
        try:
            data = yaml.safe_load(fm_str) or {}
        except Exception:
            continue
        tags = data.get("tags", [])
        if not isinstance(tags, list):
            continue
        to_remove = [t for t in tags if isinstance(t, str) and t.strip() in singleton_tags]
        if not to_remove:
            continue
        new_tags = [t for t in tags if not (isinstance(t, str) and t.strip() in singleton_tags)]
        rel = path.relative_to(cfg.vault_path)
        print(f"  {rel}: удалить {to_remove}")
        modified += 1
        if args.apply:
            data["tags"] = new_tags
            buf = __import__("io").StringIO()
            yaml.dump(data, buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            new_fm = buf.getvalue().strip()
            new_text = "---\n" + new_fm + "\n---\n" + body
            path.write_text(new_text, encoding="utf-8")

    if not args.apply and modified:
        print("\nDry-run: изменений не было. Запустите с --apply для применения.")
    print(f"Заметок, из которых будут/были удалены singleton-теги: {modified}")
    if args.apply and modified:
        print("Пересобери инвентарь: python tags_inventory.py")


if __name__ == "__main__":
    main()
