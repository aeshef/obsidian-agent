#!/usr/bin/env python3
"""
Применяет разрешение дублей:
- Контент (логика Sunshine): оставить базовую или полнейшую, переименовать в base, удалить остальные.
- Generic-серии (Без_названия_1, Без_названия_26 …): оставить одну заметку (самую полную по body),
  остальные удалить.

Удаляет Export-файлы, которые ссылаются только на удаляемые заметки.
Использует вывод analyze_vault_duplicates.py --json. По умолчанию — dry-run.
  python apply_duplicates_resolution.py
  python apply_duplicates_resolution.py --apply
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import yaml

_AGENT = Path(__file__).resolve().parent.parent.parent
if str(_AGENT) not in sys.path:
    sys.path.insert(0, str(_AGENT))

from knowledge_bot.core.config import load_config

SCRIPT_DIR = Path(__file__).resolve().parent


def get_attachment_files_from_frontmatter(frontmatter: dict) -> list[str]:
    """Из frontmatter достаёт список путей к файлам (attachments.files)."""
    att = frontmatter.get("attachments") if isinstance(frontmatter, dict) else {}
    if not isinstance(att, dict):
        return []
    files = att.get("files", [])
    if isinstance(files, list):
        return [str(f).strip() for f in files if f]
    return []


def main() -> None:
    ap = argparse.ArgumentParser(description="Применить разрешение дублей и удалить сиротские Export")
    ap.add_argument("--apply", action="store_true", help="Реально выполнить изменения")
    args = ap.parse_args()

    cfg = load_config()
    db_root = cfg.vault_path / "700_База_Данных"
    if not db_root.exists():
        print("700_База_Данных не найден", file=sys.stderr)
        sys.exit(1)

    # Получаем рекомендации из анализа дублей
    _env = {**os.environ, "VAULT_PATH": str(cfg.vault_path)}
    _pp = str(_AGENT)
    if os.environ.get("PYTHONPATH"):
        _pp = f"{_pp}{os.pathsep}{os.environ['PYTHONPATH']}"
    _env["PYTHONPATH"] = _pp
    result = subprocess.run(
        [sys.executable, str(SCRIPT_DIR / "analyze_vault_duplicates.py"), "--json"],
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
        timeout=120,
        env=_env,
    )
    if result.returncode != 0:
        print(result.stderr or result.stdout, file=sys.stderr)
        sys.exit(1)
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError as e:
        print(f"JSON parse error: {e}", file=sys.stderr)
        sys.exit(1)

    content_duplicates = data.get("content_duplicates", [])
    recommendations = data.get("content_recommendations", {})
    generic_series = data.get("generic_series", [])
    has_content = bool(recommendations)
    has_generic = any(len(g.get("notes", [])) >= 2 for g in generic_series)
    if not has_content and not has_generic:
        print("Нет групп дублей контента и нет generic-серий (2+ заметок) для применения.")
        return

    # Собираем пути заметок, которые будут удалены, и их attachments (для последующего удаления сиротских Export)
    deleted_note_paths: set[str] = set()
    attachments_from_deleted: set[str] = set()

    for item in content_duplicates:
        rec = item.get("recommendation", {}) or recommendations.get(f"{item['folder']}/{item['base_slug']}", {})
        action = rec.get("action")
        if not action:
            continue
        keep_path = rec.get("keep_path", "")
        delete_paths = rec.get("delete_paths", [])
        for note in item.get("notes", []):
            p = note.get("path", "")
            if p in delete_paths:
                deleted_note_paths.add(p)
                for ap in note.get("attachments", []):
                    if ap and "Export" in ap:
                        attachments_from_deleted.add(ap.strip())
            if action != "keep_base" and p == keep_path:
                deleted_note_paths.add(p)
                for ap in note.get("attachments", []):
                    if ap and "Export" in ap:
                        attachments_from_deleted.add(ap.strip())

    # Generic-серии: оставляем одну (самую полную), остальные считаем удаляемыми
    for item in generic_series:
        notes = item.get("notes", [])
        if len(notes) < 2:
            continue
        fullest = max(notes, key=lambda n: n.get("body_len", 0))
        keep_path = fullest.get("path", "")
        for n in notes:
            p = n.get("path", "")
            if p and p != keep_path:
                deleted_note_paths.add(p)
                for ap in n.get("attachments", []):
                    if ap and "Export" in ap:
                        attachments_from_deleted.add(ap.strip())

    dry = not args.apply
    if dry:
        print("=== DRY-RUN (запустите с --apply для применения) ===\n")

    # 1) Применяем рекомендации по заметкам
    for item in content_duplicates:
        rec = item.get("recommendation", {}) or recommendations.get(f"{item['folder']}/{item['base_slug']}", {})
        action = rec.get("action")
        keep_path = rec.get("keep_path", "")
        rename_to = rec.get("rename_to", "")
        delete_paths = rec.get("delete_paths", [])

        key = f"{item['folder']}/{item['base_slug']}"
        print(f"  [{key}] {action}")

        if action == "rename_single_to_base":
            # Одна заметка с суффиксом _N, base нет — переименовать в base
            keep_full = cfg.vault_path / keep_path
            rename_full = cfg.vault_path / rename_to
            if not keep_full.exists():
                print(f"    пропуск: нет файла {keep_path}")
                continue
            if rename_full.exists():
                print(f"    пропуск: уже есть {rename_to}")
                continue
            if dry:
                print(f"    переименовать: {keep_path} → {rename_to}")
            else:
                content = keep_full.read_text(encoding="utf-8", errors="ignore")
                rename_full.parent.mkdir(parents=True, exist_ok=True)
                rename_full.write_text(content, encoding="utf-8")
                keep_full.unlink()
                print(f"    переименован: {keep_path} → {rename_to}")
            continue

        if action == "keep_base":
            for rel in delete_paths:
                full = cfg.vault_path / rel
                if full.exists():
                    if dry:
                        print(f"    удалить: {rel}")
                    else:
                        full.unlink()
                        print(f"    удалён: {rel}")
                else:
                    print(f"    (нет файла) {rel}")
            continue

        if action in ("keep_fullest_rename", "keep_fullest_rename_then_delete_base"):
            keep_full = cfg.vault_path / keep_path
            if not keep_full.exists():
                print(f"    пропуск: нет файла {keep_path}")
                continue
            content = keep_full.read_text(encoding="utf-8", errors="ignore")
            rename_full = cfg.vault_path / rename_to
            if dry:
                print(f"    удалить: {delete_paths}")
                print(f"    записать: {rename_to} (содержимое {keep_path})")
                if keep_path != rename_to:
                    print(f"    удалить: {keep_path}")
            else:
                for rel in delete_paths:
                    f = cfg.vault_path / rel
                    if f.exists():
                        f.unlink()
                        print(f"    удалён: {rel}")
                rename_full.parent.mkdir(parents=True, exist_ok=True)
                rename_full.write_text(content, encoding="utf-8")
                print(f"    записан: {rename_to}")
                if keep_path != rename_to and (cfg.vault_path / keep_path).exists():
                    (cfg.vault_path / keep_path).unlink()
                    print(f"    удалён: {keep_path}")

    # 1.5) Generic-серии (Без_названия_1, Без_названия_26 …): оставляем одну (самую полную), остальные удаляем
    for item in generic_series:
        notes = item.get("notes", [])
        if len(notes) < 2:
            continue
        fullest = max(notes, key=lambda n: n.get("body_len", 0))
        keep_path = fullest.get("path", "")
        key = f"{item.get('folder', '')}/{item.get('base_slug', '')}"
        delete_paths = [n.get("path", "") for n in notes if n.get("path") and n.get("path") != keep_path]
        if not delete_paths:
            continue
        print(f"  [generic {key}] оставить: {keep_path}, удалить: {len(delete_paths)} шт.")
        for rel in delete_paths:
            full = cfg.vault_path / rel
            if full.exists():
                if dry:
                    print(f"    удалить: {rel}")
                else:
                    full.unlink()
                    print(f"    удалён: {rel}")
            else:
                print(f"    (нет файла) {rel}")

    # 2) Сканируем оставшиеся заметки на attachments
    # В dry-run исключаем заметки, которые будут удалены/переименованы (deleted_note_paths)
    remaining_attachments: set[str] = set()
    for path in db_root.rglob("*.md"):
        if "Export" in path.parts:
            continue
        if not path.exists():
            continue
        rel_str = str(path.relative_to(cfg.vault_path))
        if dry and rel_str in deleted_note_paths:
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except Exception:
            continue
        if not text.startswith("---"):
            continue
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
        if not match:
            continue
        try:
            fm = yaml.safe_load(match.group(1)) or {}
        except Exception:
            continue
        for ap in get_attachment_files_from_frontmatter(fm):
            if ap and "Export" in ap:
                remaining_attachments.add(ap.strip())

    # 3) Сиротские Export — были только у удалённых, у оставшихся не ссылаются
    orphan_export = [p for p in attachments_from_deleted if p not in remaining_attachments]
    orphan_export = [p for p in orphan_export if "Export" in p]

    print("\n--- Сиротские Export (ссылались только с удалённых заметок) ---")
    if not orphan_export:
        print("  Нет.")
    else:
        total_size = 0
        for rel in sorted(orphan_export):
            full = cfg.vault_path / rel
            if full.exists():
                try:
                    total_size += full.stat().st_size
                except Exception:
                    pass
                if dry:
                    print(f"  удалить: {rel}")
                else:
                    full.unlink()
                    print(f"  удалён: {rel}")
        print(f"  Файлов: {len(orphan_export)}, освобождено ~{total_size / (1024*1024):.2f} МБ")

    if dry:
        print("\nDry-run завершён. Запустите с --apply для применения.")


if __name__ == "__main__":
    main()
