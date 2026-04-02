#!/usr/bin/env python3
"""
Полный аудит domain/topic/subdomain и всех остальных неймспейсов.
Вывод для ручной проверки — что шире, что уже, что объединить.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

# Add parent for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_config
from tags_inventory import scan_all_notes


def main() -> None:
    cfg = load_config()
    inv = scan_all_notes(cfg.vault_path)
    tags = inv.get("tags", {})
    namespaces = inv.get("namespaces", {})
    total = inv.get("total_notes", 0)
    with_tags = inv.get("notes_with_tags", 0)

    print("=" * 60)
    print("АУДИТ ТЕГОВ: domain / topic / subdomain и все остальные")
    print(f"Всего заметок: {total}, с тегами: {with_tags}")
    print("=" * 60)

    # Группируем по неймспейсу
    by_ns: dict[str, list[tuple[str, int, list[str]]]] = defaultdict(list)
    for tag, info in sorted(tags.items(), key=lambda x: -x[1]["count"]):
        if "/" not in tag:
            by_ns["_other"].append((tag, info["count"], info.get("examples", [])[:2]))
            continue
        ns, value = tag.split("/", 1)
        by_ns[ns].append((value, info["count"], info.get("examples", [])[:2]))

    # Порядок неймспейсов: сначала domain, topic, source, затем остальные
    priority = ["domain", "topic", "subdomain", "source", "status", "category", "cuisine", "kind", "city", "subtype", "nsfw"]
    ordered_ns = [n for n in priority if n in by_ns]
    ordered_ns += [n for n in sorted(by_ns) if n not in ordered_ns]
    if "_other" in by_ns:
        ordered_ns.append("_other")

    for ns in ordered_ns:
        items = by_ns.get(ns, [])
        if not items:
            continue
        items.sort(key=lambda x: -x[1])  # по убыванию count
        print(f"\n## {ns.upper()} ({len(items)} значений)")
        print("-" * 50)
        for value, count, examples in items:
            ex = f"  → {examples[0]}" if examples else ""
            print(f"  {value:<35} count={count:>4}{ex}")

    print("\n" + "=" * 60)
    print("Рекомендуемая иерархия (DOMAIN_VS_TOPIC):")
    print("  domain  = широкая область (study, tech, life, travel, food, creative, business, career)")
    print("  topic   = конкретная тема (ai, ml, film, 3d-printing, finance)")
    print("  source  = откуда контент (youtube, arxiv)")
    print("  subdomain = (если используешь) — уже topic, напр. topic/3d-printing внутри domain/tech")
    print("=" * 60)


if __name__ == "__main__":
    main()
