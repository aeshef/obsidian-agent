#!/usr/bin/env python3
"""
Анализ тегов в 700_База_Данных. Только чтение, ничего не меняет.

Показывает:
- сколько тегов, топиков, доменов;
- самые популярные и самые непопулярные (в т.ч. topic/ и domain/ с 1–2 заметками);
- кандидаты на «шум» в графе (мало заметок на один тег).

Запуск: из папки knowledge_bot с настроенным VAULT_PATH или по умолчанию.
  python analyze_vault_tags.py
  python analyze_vault_tags.py --json   # вывод в JSON для последующей обработки
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Пакет knowledge_bot лежит в Agent/knowledge_bot — в sys.path нужен Agent/
_AGENT = Path(__file__).resolve().parent.parent.parent
if str(_AGENT) not in sys.path:
    sys.path.insert(0, str(_AGENT))

from knowledge_bot.core.config import load_config
from knowledge_bot.services.tags_inventory import scan_all_notes

# Выпилены из системы — не показываем в отчёте
LEGACY_NAMESPACES = frozenset({"priority", "language", "vibe"})


def main() -> None:
    ap = argparse.ArgumentParser(description="Анализ тегов хранилища (read-only)")
    ap.add_argument("--json", action="store_true", help="Вывод в JSON")
    args = ap.parse_args()

    cfg = load_config()
    inv = scan_all_notes(cfg.vault_path)
    tags = inv.get("tags", {})
    total = inv.get("total_notes", 0)
    with_tags = inv.get("notes_with_tags", 0)

    # По неймспейсам
    domain_counts: list[tuple[str, int]] = []
    topic_counts: list[tuple[str, int]] = []
    other_ns: dict[str, list[tuple[str, int]]] = {}

    for tag, info in tags.items():
        count = info.get("count", 0)
        if "/" not in tag:
            other_ns.setdefault("_other", []).append((tag, count))
            continue
        ns, value = tag.split("/", 1)
        if ns == "domain":
            domain_counts.append((value, count))
        elif ns == "topic":
            topic_counts.append((value, count))
        else:
            if ns not in LEGACY_NAMESPACES:
                other_ns.setdefault(ns, []).append((value, count))

    domain_counts.sort(key=lambda x: -x[1])
    topic_counts.sort(key=lambda x: -x[1])
    for k in other_ns:
        other_ns[k].sort(key=lambda x: -x[1])

    # Непопулярные: 1 или 2 заметки
    topic_single = [(v, c) for v, c in topic_counts if c <= 2]
    domain_single = [(v, c) for v, c in domain_counts if c <= 2]

    if args.json:
        out = {
            "total_notes": total,
            "notes_with_tags": with_tags,
            "unique_tags": len(tags),
            "domain": {"total": len(domain_counts), "by_count": domain_counts, "single_or_pair": domain_single},
            "topic": {"total": len(topic_counts), "by_count": topic_counts, "single_or_pair": topic_single},
            "other_namespaces": {k: v for k, v in other_ns.items()},
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    # Текстовый отчёт
    print("=" * 60)
    print("АНАЛИЗ ТЕГОВ ХРАНИЛИЩА (700_База_Данных)")
    print("=" * 60)
    print(f"Всего заметок: {total}, с тегами: {with_tags}")
    print(f"Уникальных тегов: {len(tags)}")
    print()

    print("## DOMAIN — по популярности (топ-30)")
    print("-" * 50)
    for value, count in domain_counts[:30]:
        print(f"  {value:<40} {count:>5} заметок")
    print()

    print("## TOPIC — по популярности (топ-40)")
    print("-" * 50)
    for value, count in topic_counts[:40]:
        print(f"  {value:<40} {count:>5} заметок")
    print()

    print("## TOPIC с 1–2 заметками (кандидаты на шум в графе)")
    print("-" * 50)
    print(f"  Всего таких topic: {len(topic_single)}")
    for value, count in sorted(topic_single, key=lambda x: (x[1], x[0])):
        print(f"  topic/{value:<35} {count:>2} заметок")
    print()

    print("## DOMAIN с 1–2 заметками")
    print("-" * 50)
    print(f"  Всего таких domain: {len(domain_single)}")
    for value, count in sorted(domain_single, key=lambda x: (x[1], x[0])):
        print(f"  domain/{value:<35} {count:>2} заметок")
    print()

    print("## Остальные неймспейсы (сводка)")
    print("-" * 50)
    for ns in sorted(other_ns.keys()):
        if ns in LEGACY_NAMESPACES:
            continue
        items = other_ns[ns]
        print(f"  {ns}: {len(items)} значений, топ по частоте: {items[:5]}")
    print("=" * 60)


if __name__ == "__main__":
    main()
