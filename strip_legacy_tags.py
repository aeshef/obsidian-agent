#!/usr/bin/env python3
"""
Удаляет из заметок 700_База_Данных теги priority/*, language/*, vibe/* (выпилены из системы).

По умолчанию — dry-run (только печать, без изменений).
  python strip_legacy_tags.py
  python strip_legacy_tags.py --apply   # реально изменить файлы
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_config

LEGACY_PREFIXES = ("priority/", "language/", "vibe/")


def strip_legacy_from_tags(tags: list) -> tuple[list, list]:
    """Возвращает (новый список тегов без legacy, список удалённых)."""
    if not isinstance(tags, list):
        return (list(tags) if tags else []), []
    removed = [t for t in tags if isinstance(t, str) and any(t.strip().startswith(p) for p in LEGACY_PREFIXES)]
    new_tags = [t for t in tags if not (isinstance(t, str) and any(t.strip().startswith(p) for p in LEGACY_PREFIXES))]
    return new_tags, removed


def main() -> None:
    ap = argparse.ArgumentParser(description="Удалить priority/language/vibe теги из заметок")
    ap.add_argument("--apply", action="store_true", help="Реально изменить файлы (иначе dry-run)")
    args = ap.parse_args()

    cfg = load_config()
    db_root = cfg.vault_path / "700_База_Данных"
    if not db_root.exists():
        print("700_База_Данных не найден", file=sys.stderr)
        sys.exit(1)

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
        new_tags, removed = strip_legacy_from_tags(tags)
        if not removed:
            continue
        rel = path.relative_to(cfg.vault_path)
        print(f"  {rel}: удалить {removed}")
        modified += 1
        if args.apply:
            data["tags"] = new_tags
            # Сериализуем YAML без изменения порядка полей по возможности
            import io
            buf = io.StringIO()
            yaml.dump(data, buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            new_fm = buf.getvalue().strip()
            new_text = "---\n" + new_fm + "\n---\n" + body
            path.write_text(new_text, encoding="utf-8")

    if not args.apply and modified:
        print("\nDry-run: изменений не было. Запустите с --apply для применения.")
    print(f"Заметок с legacy-тегами: {modified}")


if __name__ == "__main__":
    main()
