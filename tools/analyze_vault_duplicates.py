#!/usr/bin/env python3
"""
Анализ дублей в 700_База_Данных (названия с суффиксом _1, _2, _3). Только чтение.

Разделяет:
1) Серии (generic) — Без_названия, База_Данных/База_данных и т.п.: модель не смогла
   извлечь контекст или контекст плохой. Рекомендация: дедуплицировать, попробовать
   вытащить контекст / прогнать пайплайн; иначе удалить.
2) Дубли контента — один и тот же смысл (например Sunshine_2007_1 и _2). Рекомендация:
   оставить одну самую полную заметку, переименовать в base_slug.md (без суффикса),
   остальные удалить. Если уже есть заметка base_slug.md — оставить полнейшую из всех.

Показывает также: какая заметка в группе полнее; есть ли уже заметка без суффикса;
файлы Export, на которые ссылаются дубли.

Запуск: из папки knowledge_bot.
  python analyze_vault_duplicates.py
  python analyze_vault_duplicates.py --json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))

from knowledge_bot.core.config import load_config

# «Серии» — generic-названия, когда модель не смогла нормально назвать (нет/плохой контекст).
# Одинаковые по смыслу варианты (База_Данных / База_данных) считаем одной серией по lower().
GENERIC_BASE_SLUGS = frozenset({"без_названия", "база_данных", "img"})


def parse_note(path: Path) -> tuple[dict, str]:
    """Читает заметку, возвращает (frontmatter_dict, body)."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return {}, ""
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", text, re.DOTALL)
    if not match:
        return {}, text
    fm_str, body = match.group(1), match.group(2)
    try:
        data = yaml.safe_load(fm_str) or {}
        return data if isinstance(data, dict) else {}, body
    except Exception:
        return {}, body


def get_attachment_files(frontmatter: dict) -> list[str]:
    """Из frontmatter достаёт список путей к файлам (attachments.files)."""
    att = frontmatter.get("attachments")
    if not isinstance(att, dict):
        return []
    files = att.get("files")
    if isinstance(files, list):
        return [str(f).strip() for f in files if f]
    return []


def main() -> None:
    ap = argparse.ArgumentParser(description="Анализ дублей по названиям _1, _2, _3 (read-only)")
    ap.add_argument("--json", action="store_true", help="Вывод в JSON")
    args = ap.parse_args()

    cfg = load_config()
    db_root = cfg.vault_path / "700_База_Данных"
    if not db_root.exists():
        print("700_База_Данных не найден", file=sys.stderr)
        sys.exit(1)

    # Собираем все .md, кроме Export
    notes: list[Path] = []
    for p in db_root.rglob("*.md"):
        if "Export" in p.parts:
            continue
        notes.append(p)

    # Разбираем по stem: (folder, base_slug) -> list of (path, suffix_num, body_len, attachment_paths)
    suffix_re = re.compile(r"^(.+)_(\d+)$")
    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    notes_with_suffix = 0
    total_duplicate_notes = 0  # число заметок, входящих в какую-то группу дублей

    for path in notes:
        rel = path.relative_to(cfg.vault_path)
        # rel = 700_База_Данных/Личности/file.md -> folder = Личности
        folder = rel.parts[1] if len(rel.parts) >= 2 else ""
        stem = path.stem
        m = suffix_re.match(stem)
        if not m:
            continue
        base_slug, num_str = m.group(1), m.group(2)
        notes_with_suffix += 1
        fm, body = parse_note(path)
        body_len = len(body.strip())
        attachments = get_attachment_files(fm)
        key = (folder, base_slug)
        groups[key].append({
            "path": str(rel),
            "suffix": int(num_str),
            "body_len": body_len,
            "attachments": attachments,
            "title": fm.get("title") or stem,
            "type": fm.get("type"),
        })

    # Группы с 2+ заметками — дубли (объединяем/удаляем)
    duplicate_groups = {k: sorted(v, key=lambda x: x["suffix"]) for k, v in groups.items() if len(v) >= 2}
    for g in duplicate_groups.values():
        total_duplicate_notes += len(g)

    # Одиночные суффиксы: одна заметка X_1 (или _2) в папке, base X.md нет — просто переименовать в X.md
    single_suffix_groups = {k: sorted(v, key=lambda x: x["suffix"]) for k, v in groups.items() if len(v) == 1}

    # Разделяем на серии (generic) и дубли контента
    generic_series = {}
    content_duplicates = {}
    for k, g in duplicate_groups.items():
        folder, base_slug = k[0], k[1]
        if base_slug.lower() in GENERIC_BASE_SLUGS:
            generic_series[k] = g
        else:
            content_duplicates[k] = g

    # Для каждой группы помечаем «полнейшую» заметку (по body_len)
    for g in duplicate_groups.values():
        max_len = max(x["body_len"] for x in g)
        for x in g:
            x["is_fullest"] = x["body_len"] == max_len and max_len >= 0

    # Проверяем наличие заметки без суффикса (base_slug.md) и формируем рекомендации для контент-дублей
    content_recommendations: dict[tuple[str, str], dict] = {}
    for (folder, base_slug), g in content_duplicates.items():
        base_note_path = db_root / folder / f"{base_slug}.md"
        base_exists = base_note_path.exists()
        fullest_in_group = max(g, key=lambda x: x["body_len"])
        base_rel = str(Path("700_База_Данных") / folder / f"{base_slug}.md")
        if base_exists:
            try:
                _, base_body = parse_note(base_note_path)
                base_len = len(base_body.strip())
                if base_len >= fullest_in_group["body_len"]:
                    content_recommendations[(folder, base_slug)] = {
                        "base_exists": True,
                        "keep_path": base_rel,
                        "action": "keep_base",
                        "delete_paths": [x["path"] for x in g],
                    }
                else:
                    content_recommendations[(folder, base_slug)] = {
                        "base_exists": True,
                        "keep_path": fullest_in_group["path"],
                        "action": "keep_fullest_rename_then_delete_base",
                        "rename_to": base_rel,
                        "delete_paths": [x["path"] for x in g if x["path"] != fullest_in_group["path"]] + [base_rel],
                    }
            except Exception:
                content_recommendations[(folder, base_slug)] = {
                    "base_exists": True,
                    "keep_path": fullest_in_group["path"],
                    "action": "keep_fullest_rename",
                    "rename_to": base_rel,
                    "delete_paths": [x["path"] for x in g if x["path"] != fullest_in_group["path"]],
                }
        else:
            content_recommendations[(folder, base_slug)] = {
                "base_exists": False,
                "keep_path": fullest_in_group["path"],
                "action": "keep_fullest_rename",
                "rename_to": base_rel,
                "delete_paths": [x["path"] for x in g if x["path"] != fullest_in_group["path"]],
            }

    # Рекомендации для одиночных суффиксов
    for (folder, base_slug), g in single_suffix_groups.items():
        if base_slug.lower() in GENERIC_BASE_SLUGS:
            continue
        base_note_path = db_root / folder / f"{base_slug}.md"
        base_rel = str(Path("700_База_Данных") / folder / f"{base_slug}.md")
        content_duplicates[(folder, base_slug)] = g
        if base_note_path.exists():
            # Уже есть base — лишнюю заметку _1 удалить (оставить base)
            content_recommendations[(folder, base_slug)] = {
                "base_exists": True,
                "keep_path": base_rel,
                "action": "keep_base",
                "delete_paths": [g[0]["path"]],
            }
        else:
            # base нет — переименовать _N → base
            content_recommendations[(folder, base_slug)] = {
                "base_exists": False,
                "keep_path": g[0]["path"],
                "action": "rename_single_to_base",
                "rename_to": base_rel,
                "delete_paths": [],
            }

    # Собираем все Export-файлы, на которые ссылаются дубли
    export_files: dict[str, int] = {}  # path -> size
    for g in duplicate_groups.values():
        for x in g:
            for ap in x["attachments"]:
                if "Export" not in ap:
                    continue
                full = cfg.vault_path / ap
                if full.exists():
                    try:
                        export_files[ap] = full.stat().st_size
                    except Exception:
                        pass

    if args.json:
        def _serialize_group(g: list) -> list:
            return [{k: v for k, v in x.items() if not k.startswith("_")} for x in g]
        out = {
            "total_notes_scanned": len(notes),
            "notes_with_suffix_1_2_3": notes_with_suffix,
            "generic_series_count": len(generic_series),
            "content_duplicates_count": len(content_duplicates),
            "generic_series": [
                {"folder": k[0], "base_slug": k[1], "notes": _serialize_group(g), "note_count": len(g)}
                for k, g in sorted(generic_series.items(), key=lambda x: -len(x[1]))
            ],
            "content_duplicates": [
                {
                    "folder": k[0],
                    "base_slug": k[1],
                    "notes": _serialize_group(g),
                    "recommendation": content_recommendations.get(k, {}),
                }
                for k, g in sorted(content_duplicates.items(), key=lambda x: -len(x[1]))
            ],
            "content_recommendations": {
                f"{k[0]}/{k[1]}": content_recommendations[k]
                for k in content_duplicates
            },
            "export_files_referenced_by_duplicates": [
                {"path": p, "size_bytes": s} for p, s in sorted(export_files.items(), key=lambda x: -x[1])
            ],
            "export_total_size_bytes": sum(export_files.values()),
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return

    # Текстовый отчёт
    print("=" * 60)
    print("АНАЛИЗ ДУБЛЕЙ (названия с суффиксом _1, _2, _3)")
    print("=" * 60)
    print(f"Всего заметок в 700_База_Данных (без Export): {len(notes)}")
    print(f"Из них с суффиксом _N в имени: {notes_with_suffix}")
    print(f"Групп дублей (≥2 заметки): {len(duplicate_groups)}")
    print(f"  — серии (generic): {len(generic_series)} групп")
    print(f"  — дубли контента: {len(content_duplicates)} групп")
    print()

    print("## 1. Серии (generic) — Без_названия, База_Данных и т.п.")
    print("    Контекст не извлечён или плохой. Рекомендация: дедуплицировать;")
    print("    попробовать вытащить контекст / прогнать пайплайн; иначе удалить.")
    print("-" * 60)
    for (folder, base_slug), g in sorted(generic_series.items(), key=lambda x: -len(x[1])):
        print(f"\n  [{folder}] {base_slug}  ({len(g)} заметок)")
        for x in g:
            mark = " [FULLEST]" if x.get("is_fullest") else ""
            att_info = f", {len(x['attachments'])} файл(ов)" if x["attachments"] else ""
            print(f"    → {x['path']}  body={x['body_len']} симв.{att_info}{mark}")
    print()

    print("## 2. Дубли контента — оставить полнейшую, переименовать в base.md, остальных удалить")
    print("-" * 60)
    for (folder, base_slug), g in sorted(content_duplicates.items(), key=lambda x: (-len(x[1]), x[0])):
        rec = content_recommendations.get((folder, base_slug), {})
        action = rec.get("action", "")
        keep = rec.get("keep_path", "")
        rename_to = rec.get("rename_to", "")
        delete_list = rec.get("delete_paths", [])
        print(f"\n  [{folder}] {base_slug}  ({len(g)} заметок)")
        for x in g:
            mark = " [FULLEST]" if x.get("is_fullest") else ""
            att_info = f", {len(x['attachments'])} файл(ов)" if x["attachments"] else ""
            print(f"    → {x['path']}  body={x['body_len']} симв.{att_info}{mark}")
        print(f"    Рекомендация: {action}")
        print(f"    Оставить: {keep}")
        if rename_to:
            print(f"    Переименовать в: {rename_to}")
        if delete_list:
            print(f"    Удалить: {delete_list}")
    print()

    print("## 3. Файлы Export, на которые ссылаются дубли")
    print("-" * 60)
    total_size = sum(export_files.values())
    print(f"  Всего файлов: {len(export_files)}, суммарный размер: {total_size / (1024*1024):.2f} МБ")
    for p, size in sorted(export_files.items(), key=lambda x: -x[1])[:40]:
        print(f"  {size:>10}  {p}")
    if len(export_files) > 40:
        print(f"  ... и ещё {len(export_files) - 40} файлов")
    print("=" * 60)


if __name__ == "__main__":
    main()
