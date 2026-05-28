#!/usr/bin/env python3
"""
Чистка singleton-тегов (count=1): для каждой заметки передаём текущие теги и сколько
раз каждый тег встречается в базе. LLM решает по каждому тегу — оставить или убрать:
общие/важные (например genetics) оставить, специфичные/шумные (gt40, hot-wheels) убрать.
Новые теги не добавляются, только keep/remove из текущего набора.

Требует DEEPSEEK_API_KEY в окружении (или .env).
  python refill_singleton_tags.py              # dry-run
  python refill_singleton_tags.py --apply       # записать теги
  python refill_singleton_tags.py --apply --limit 10   # только первые 10 заметок
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

# Подгрузка .env (как в reprocess_notes / apply_wikilinks_batch)
for _p in [Path(__file__).resolve().parent / ".env", Path(__file__).resolve().parent.parent / ".env"]:
    if _p.exists():
        for _line in _p.read_text(encoding="utf-8", errors="ignore").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                if _k.strip():
                    os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))

from knowledge_bot.core.config import load_config
from knowledge_bot.services.tags_inventory import scan_all_notes
from knowledge_bot.core.settings import load_enums_config
from knowledge_bot.core.llm import LLMClient

REFILL_SYSTEM = """Задача: у заметки есть список тегов. Для каждого тега указано, сколько заметок в базе знаний его используют (count).

Правила:
- Теги с count=1 (синглтоны) — редко встречаются. Реши по смыслу: ОСТАВИТЬ или УБРАТЬ.
- ОСТАВИТЬ: тег важный и общий (например topic/genetics, topic/archaeology — одна заметка, но тема значимая для навигации).
- УБРАТЬ: тег специфичный/шумный (например topic/gt40, topic/hot-wheels, topic/subtitles — слишком узкий или мусорный).

Теги с count>=2 не трогай — оставляй. Не добавляй новых тегов, только выбери подмножество текущих (какие оставить).

Вход: type заметки, краткий контекст (body), current_tags_with_counts — список {"tag": "topic/...", "count": N}.
Выход: JSON с одним полем "tags" — массив строк, только те теги, которые должны остаться у заметки. Без комментариев."""


from knowledge_bot.services.tag_normalize import normalize_tags


def main() -> None:
    ap = argparse.ArgumentParser(description="Оставить/убрать singleton-теги по решению LLM (count в промпте, без добавления новых)")
    ap.add_argument("--apply", action="store_true", help="Записать новые теги в заметки")
    ap.add_argument("--limit", type=int, default=0, help="Максимум заметок обработать (0 = все)")
    args = ap.parse_args()

    cfg = load_config()
    db_root = cfg.vault_path / "700_База_Данных"
    if not db_root.exists():
        print("700_База_Данных не найден", file=sys.stderr)
        sys.exit(1)

    if not cfg.deepseek_api_key:
        print("Нужен DEEPSEEK_API_KEY в окружении (или задай в .env и загрузи вручную).", file=sys.stderr)
        sys.exit(1)

    inv = scan_all_notes(cfg.vault_path)
    tags_data = inv.get("tags", {})
    singleton_tags = {tag for tag, info in tags_data.items() if info.get("count", 0) == 1}
    if not singleton_tags:
        print("Нет тегов с 1 заметкой. Нечего перезаполнять.")
        return

    # Собираем заметки, у которых есть хотя бы один singleton-тег
    notes_to_refill: list[tuple[Path, dict, str, list[str]]] = []  # path, fm, body, current_tags
    for path in sorted(db_root.rglob("*.md")):
        if "Export" in path.parts:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        m = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
        if not m:
            continue
        fm_str, body = m.group(1), m.group(2)
        try:
            data = yaml.safe_load(fm_str) or {}
        except Exception:
            continue
        tags = data.get("tags", [])
        if not isinstance(tags, list):
            continue
        tags_set = {str(t).strip() for t in tags if t}
        has_singleton = bool(tags_set & singleton_tags)
        if not has_singleton:
            continue
        notes_to_refill.append((path, data, body, list(tags_set)))

    if not notes_to_refill:
        print("Нет заметок с singleton-тегами.")
        return

    if args.limit:
        notes_to_refill = notes_to_refill[: args.limit]
    print(f"Заметок к перезаполнению тегов: {len(notes_to_refill)}")
    if not args.apply:
        print("=== DRY-RUN (запустите с --apply для записи) ===\n")

    enums_cfg = load_enums_config(cfg.agent_config_path)
    llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
    modified = 0
    for path, data, body, current_tags in notes_to_refill:
        rel = path.relative_to(cfg.vault_path)
        note_type = data.get("type") or "Знания"
        body_preview = (body.strip() or "")[:1500]
        tags_with_counts = [
            {"tag": t, "count": tags_data.get(t, {}).get("count", 0)}
            for t in current_tags
        ]
        tags_user = {
            "type": note_type,
            "body_preview": body_preview,
            "current_tags_with_counts": tags_with_counts,
        }
        try:
            tag_resp = llm.chat_json(REFILL_SYSTEM, json.dumps(tags_user, ensure_ascii=False)).content
        except Exception as e:
            print(f"  {rel}: LLM error — {e}", file=sys.stderr)
            continue
        if isinstance(tag_resp, dict) and "tags" in tag_resp:
            tag_candidates = tag_resp.get("tags") or []
        else:
            tag_candidates = tag_resp if isinstance(tag_resp, list) else []
        new_tags = normalize_tags(tag_candidates, enums_cfg, note_type, allowed_tags=set(current_tags))
        if not new_tags:
            new_tags = list(current_tags)
        print(f"  {rel}: было {current_tags} → стало {new_tags}")
        if args.apply and set(new_tags) != set(current_tags):
            data["tags"] = new_tags
            buf = __import__("io").StringIO()
            yaml.dump(data, buf, allow_unicode=True, default_flow_style=False, sort_keys=False)
            new_fm = buf.getvalue().strip()
            new_text = "---\n" + new_fm + "\n---\n" + body
            path.write_text(new_text, encoding="utf-8")
            modified += 1

    if args.apply and modified:
        print(f"\nОбновлено заметок: {modified}. Пересобери инвентарь: python tags_inventory.py")
    elif not args.apply:
        print("\nDry-run завершён. Запустите с --apply для записи.")


if __name__ == "__main__":
    main()
