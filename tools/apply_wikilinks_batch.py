#!/usr/bin/env python3
"""
Применяет [[wikilinks]] к существующим заметкам (как для новых при создании через бота).

  python apply_wikilinks_batch.py              # превью (dry-run)
  python apply_wikilinks_batch.py --apply      # записать
  python apply_wikilinks_batch.py --limit 20   # только первые 20 заметок
  python apply_wikilinks_batch.py --vault /path/to/vault
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Подгрузка .env
for _p in [Path(__file__).resolve().parent / ".env", Path(__file__).resolve().parent.parent / ".env"]:
    if _p.exists():
        for _line in _p.read_text().splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                import os
                os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))
        break

# пакет knowledge_bot: родительский каталог — Agent/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from knowledge_bot.core.config import load_config
from knowledge_bot.core.llm import LLMClient
from knowledge_bot.services.wikilinks import inject_wikilinks, get_candidates, body_has_any_candidate


def main() -> None:
    apply = "--apply" in sys.argv or "-apply" in sys.argv
    limit = None
    vault_override = None
    for i, a in enumerate(sys.argv):
        if a == "--vault" and i + 1 < len(sys.argv):
            vault_override = Path(sys.argv[i + 1]).resolve()
        elif a == "--limit" and i + 1 < len(sys.argv):
            try:
                limit = int(sys.argv[i + 1])
            except ValueError:
                limit = 20
    if vault_override:
        import os
        os.environ["VAULT_PATH"] = str(vault_override)
    cfg = load_config()
    vault = vault_override or cfg.vault_path
    db_root = vault / "700_База_Данных"
    if not db_root.exists():
        print(f"  db_root не найден: {db_root}")
        return
    llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
    notes = sorted(n for n in db_root.rglob("*.md") if "Export" not in str(n))
    if limit:
        notes = notes[:limit]
        print(f"Обрабатываем (limit={limit}): {len(notes)} заметок")
    else:
        print(f"Найдено заметок: {len(notes)}")
    if not notes:
        return
    candidates = get_candidates(vault, cfg.agent_config_path)
    print(f"Кандидатов wikilinks: {len(candidates)}")
    modified = 0
    skipped = 0
    for i, note_path in enumerate(notes):
        if (i + 1) % 50 == 0 or (i == 0 and len(notes) > 20):
            print(f"  ... {i + 1}/{len(notes)}")
        try:
            text = note_path.read_text(encoding="utf-8", errors="ignore")
        except Exception as e:
            print(f"  Ошибка {note_path.name}: {e}")
            continue
        m = re.match(r"^(---\s*\n.*?\n---\s*\n)(.*)$", text, re.DOTALL)
        if not m:
            skipped += 1
            continue
        frontmatter_block, body = m.groups()
        if len(body.strip()) < 50:
            skipped += 1
            continue
        if not body_has_any_candidate(body, candidates):
            skipped += 1
            continue
        new_body = inject_wikilinks(body, cfg.agent_config_path, vault, llm)
        if new_body == body:
            continue
        new_text = frontmatter_block + new_body
        rel = note_path.relative_to(vault)
        print(f"  ✓ {rel}")
        if apply:
            note_path.write_text(new_text, encoding="utf-8")
            modified += 1
    print(f"\nИзменено: {modified} (пропущено: {skipped})")
    if not apply:
        print("(dry-run, для записи добавь --apply)")


if __name__ == "__main__":
    main()
