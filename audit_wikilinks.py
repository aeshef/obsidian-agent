#!/usr/bin/env python3
"""
Сбор кандидатов на wikilinks + частотный анализ в тексте заметок.
Помогает понять: какие термины встречаются в заметках и куда могли бы ссылаться.
"""
from __future__ import annotations

import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

# Add parent for imports
sys.path.insert(0, str(Path(__file__).resolve().parent))

from config import load_config
from tags_inventory import load_tags_inventory, scan_all_notes


def extract_body_text(note_path: Path) -> str:
    """Текст заметки без frontmatter (body)."""
    try:
        text = note_path.read_text(encoding="utf-8", errors="ignore")
        m = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
        return text[m.end() :] if m else text
    except Exception:
        return ""


def tokenize_for_wikilinks(text: str) -> list[str]:
    """Токены: слова (включая camelCase, snake_case) + числа в контексте."""
    text = text.lower()
    # Оставляем буквы, цифры, дефисы, подчёркивания
    tokens = re.findall(r"[a-zа-яё0-9]+(?:[-_][a-zа-яё0-9]+)*", text)
    return [t for t in tokens if len(t) >= 2]  # минимум 2 символа


def main() -> None:
    cfg = load_config()
    agent_config = cfg.agent_config_path
    db_root = cfg.vault_path / "700_База_Данных"
    if not db_root.exists():
        print("700_База_Данных не найден")
        return

    # 1) Кандидаты из tags_inventory (topic/*, domain/*)
    inv = load_tags_inventory(agent_config)
    tags_dict = inv.get("tags", {})
    candidates: dict[str, tuple[str, int]] = {}  # keyword -> (wikilink, count)
    for tag, info in tags_dict.items():
        if "/" not in tag:
            continue
        ns, value = tag.split("/", 1)
        if ns not in ("topic", "domain"):
            continue
        examples = info.get("examples") or []
        if not examples:
            continue
        link = str(examples[0]).replace("\\", "/").rstrip(".md")
        keyword = value.strip()
        if len(keyword) < 2:
            continue
        count = info.get("count", 0)
        if keyword not in candidates or count > candidates[keyword][1]:
            candidates[keyword] = (link, count)

    # 2) Частотный анализ в тексте заметок
    body_freq: Counter[str] = Counter()
    note_titles: dict[str, str] = {}  # slug -> path для потенциальных ссылок по названиям
    for note_path in db_root.rglob("*.md"):
        if "Export" in str(note_path):
            continue
        rel = note_path.relative_to(cfg.vault_path)
        slug = note_path.stem.replace(" ", "_")
        note_titles[slug.lower()] = str(rel).replace("\\", "/").rstrip(".md")
        body = extract_body_text(note_path)
        body_freq.update(tokenize_for_wikilinks(body))

    # 3) Сводка: кандидаты из тегов + их частота в тексте
    print("=" * 70)
    print("КАНДИДАТЫ НА WIKILINKS (из topic/domain)")
    print("=" * 70)
    print(f"{'keyword':<30} {'в тексте':>8} {'в тегах':>8}  → target")
    print("-" * 70)
    rows = []
    for kw, (link, tag_count) in sorted(candidates.items(), key=lambda x: -x[1][1]):
        in_body = body_freq.get(kw, 0) + body_freq.get(kw.replace("-", "_"), 0)
        rows.append((kw, in_body, tag_count, link))
    for kw, in_body, tag_count, link in sorted(rows, key=lambda x: -(x[1] + x[2] * 10)):
        print(f"{kw:<30} {in_body:>8} {tag_count:>8}  → {link[:50]}")

    # 4) Топ токенов в тексте, которых НЕТ в кандидатах (потенциальные новые)
    print("\n" + "=" * 70)
    print("ТОП СЛОВ В ТЕКСТЕ ЗАМЕТОК (без учёта стоп-слов, нет в topic/domain)")
    print("=" * 70)
    stop = {
        "the", "and", "for", "that", "this", "with", "from", "are", "was", "were", "been", "have", "has", "had", "will", "would", "could", "should", "can", "may", "etc", "url", "http", "https", "www", "com", "org", "html", "md", "jpg", "png", "mp4",
        "на", "не", "для", "что", "это", "как", "или", "по", "но", "to", "you", "if", "за", "вы", "из", "от", "так", "без", "все", "ты", "можно", "есть", "of", "то", "мы", "be", "до", "он", "только", "in",
        "ключевые", "тезисы", "текст", "шаги", "изображения", "исходный", "файлы", "транскрипция", "сводка", "asr", "кратко", "конкретные", "советы", "факты", "ссылки", "инсайты", "actionable", "субтитров", "следующие", "гипотеза", "видео", "музыка",
        "export", "700_база_данных", "2026", "01",
    }
    candidate_keys = {k.lower() for k in candidates} | {k.replace("-", "_") for k in candidates}
    extra = [(w, c) for w, c in body_freq.most_common(150) if w not in stop and w not in candidate_keys and c >= 2]
    for word, cnt in extra[:60]:
        print(f"  {word:<25} {cnt:>5}")

    # 5) Имена заметок, встречающиеся в тексте (кандидаты по названию)
    print("\n" + "=" * 70)
    print("ИМЕНА ЗАМЕТОК, ВСТРЕЧАЮЩИЕСЯ В ТЕКСТЕ (кандидаты для [[по названию]])")
    print("=" * 70)
    note_in_body = [(s, p, body_freq.get(s, 0) + body_freq.get(s.replace("_", "-"), 0)) for s, p in note_titles.items()]
    note_in_body = [(s, p, c) for s, p, c in note_in_body if c > 0 and 4 <= len(s) <= 35]
    for slug, path, cnt in sorted(note_in_body, key=lambda x: -x[2])[:35]:
        print(f"  {slug:<35} в тексте={cnt:>3}  → {path[:50]}")

    print("\n" + "=" * 70)
    print("ВАРИАНТЫ ДАЛЬШЕ:")
    print("  1. Ограничить wikilinks только topic/domain с in_text >= N")
    print("  2. LLM выбирает keywords для конкретной заметки → regex подставляет [[...]]")
    print("  3. Whitelist: только высокочастотные и нешумные (ai, ml, python, etc)")
    print("=" * 70)


if __name__ == "__main__":
    main()
