#!/usr/bin/env python3
"""
Унифицирует domain/X и topic/X при одном и том же X:
- Если в заметке есть и domain/X, и topic/X — удаляем topic/X (дубль).
- Если значение X — каноническая «область жизни», а в заметке только topic/X —
  заменяем topic/X на domain/X (единый неймспейс для travel, food, study и т.д.).

По умолчанию — dry-run.
  python unify_domain_topic.py
  python unify_domain_topic.py --apply
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from knowledge_bot.core.config import load_config
from shared.vault_layout import knowledge_subdir

# Значения, которые по смыслу — domain (область жизни), не topic
CANONICAL_DOMAIN_VALUES = frozenset({
    "travel", "food", "study", "tech", "life", "creative", "business", "career",
    "education", "entertainment",
})


def main() -> None:
    ap = argparse.ArgumentParser(description="Унифицировать domain/X и topic/X с одинаковым X")
    ap.add_argument("--apply", action="store_true", help="Реально изменить файлы (иначе dry-run)")
    args = ap.parse_args()

    cfg = load_config()
    kd = knowledge_subdir()
    db_root = cfg.vault_path / kd
    if not db_root.exists():
        print(f"{kd} не найден", file=sys.stderr)
        sys.exit(1)

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
        tags_set = {str(t).strip() for t in tags if isinstance(t, str) and t.strip()}
        domain_values = {t.split("/", 1)[1] for t in tags_set if t.startswith("domain/") and "/" in t}
        to_remove: set[str] = set()
        to_add: set[str] = set()

        # 1) Убрать topic/X, если есть domain/X (дубль)
        for t in tags_set:
            if t.startswith("topic/") and "/" in t:
                val = t.split("/", 1)[1]
                if val in domain_values:
                    to_remove.add(t)

        # 2) topic/X → domain/X для канонических областей, если domain/X ещё нет
        for t in list(tags_set):
            if t.startswith("topic/") and "/" in t:
                val = t.split("/", 1)[1]
                if val in CANONICAL_DOMAIN_VALUES and f"domain/{val}" not in tags_set:
                    to_remove.add(t)
                    to_add.add(f"domain/{val}")

        if not to_remove and not to_add:
            continue
        # to_add без дублей с to_remove (если заменили topic/X на domain/X, только один domain/X в итоге)
        new_tags = [t for t in tags if not (isinstance(t, str) and t.strip() in to_remove)]
        for a in to_add:
            if a not in {str(x).strip() for x in new_tags}:
                new_tags.append(a)
        rel = path.relative_to(cfg.vault_path)
        if to_remove:
            print(f"  {rel}: убрать {sorted(to_remove)}")
        if to_add:
            print(f"    добавить {sorted(to_add)}")
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
    print(f"Заметок к изменению: {modified}")
    if args.apply and modified:
        print("Пересобери инвентарь: python tags_inventory.py")


if __name__ == "__main__":
    main()
