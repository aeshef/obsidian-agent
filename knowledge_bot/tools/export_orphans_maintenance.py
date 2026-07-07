#!/usr/bin/env python3
"""Audit/rehydrate/cleanup unreferenced files in 700_/Export."""
from __future__ import annotations

import argparse
import os
import re
import sys
from datetime import date
from pathlib import Path

import yaml

package_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(package_root.parent))

from knowledge_bot.core.config import load_config
from knowledge_bot.core.llm import LLMClient
from knowledge_bot.services.export_refs import (
    collect_export_inventory,
    normalize_export_ref,
)
from knowledge_bot.services.extract import extract_from_path
from knowledge_bot.services.persist import write_note
from knowledge_bot.services.render import render_note
from knowledge_bot.services.routing import route_and_fill
from shared.vault_layout import knowledge_subdir


def _parse_args() -> argparse.Namespace:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", type=Path, default=None)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--rehydrate-limit", type=int, default=0)
    ap.add_argument("--rehydrate-max-mb", type=int, default=25)
    ap.add_argument("--allow-delete", action="store_true")
    ap.add_argument("--delete-cap", type=int, default=300)
    ap.add_argument("--cleanup-broken-refs", action="store_true")
    ap.add_argument("--cleanup-broken-body-refs", action="store_true")
    ap.add_argument("--print-limit", type=int, default=100)
    return ap.parse_args()


def _guess_form(rel_export_path: str) -> str:
    ext = Path(rel_export_path).suffix.lower()
    if ext in {".mp4", ".mov", ".avi", ".mkv", ".webm"}:
        return "video"
    if ext in {".mp3", ".ogg", ".wav", ".m4a"}:
        return "audio"
    if ext in {".jpg", ".jpeg", ".png", ".gif", ".webp"}:
        return "photo"
    if ext in {".pdf"}:
        return "document"
    return "file"


def _rehydrate_orphans(
    *,
    vault: Path,
    rel_paths: list[str],
    limit: int,
    max_mb: int,
    cfg,
) -> tuple[int, list[str]]:
    if limit <= 0 or not rel_paths:
        return 0, []
    llm = LLMClient(cfg.deepseek_api_key, cfg.deepseek_base_url)
    db_root = vault / knowledge_subdir()
    written = 0
    consumed: list[str] = []
    for rel in rel_paths[:limit]:
        full = db_root / "Export" / rel
        if not full.exists() or not full.is_file():
            continue
        try:
            if max_mb > 0 and (full.stat().st_size / (1024 * 1024)) > max_mb:
                print(f"REHYDRATE_EXPORT_SKIPPED_SIZE: {rel}")
                continue
        except OSError:
            continue
        form = _guess_form(rel)
        summary_obj = {
            "raw_text": f"Recovered orphan export file: {Path(rel).name}",
            "meta": {"form": form},
            "derived": {},
        }
        try:
            derived = extract_from_path(str(full), llm_client=llm)
            if derived.asr_text:
                summary_obj["derived"]["asr_text"] = derived.asr_text
            if derived.vision_text:
                summary_obj["derived"]["vision_text"] = derived.vision_text
            if derived.ocr_text:
                summary_obj["derived"]["ocr_text"] = derived.ocr_text
            if derived.pdf_text:
                summary_obj["derived"]["pdf_text"] = derived.pdf_text
        except Exception:
            # Continue with minimal summary when enrichment fails.
            pass
        try:
            routed = route_and_fill(llm, summary_obj, source_hint="maintenance_export_orphan")
            routed.setdefault("attachments", {"links": [], "files": []})
            routed["attachments"]["files"] = [
                f"{knowledge_subdir()}/Export/{rel}",
            ]
            routed["attachments"]["links"] = routed["attachments"].get("links", []) or []
            routed.setdefault("form", form)
            routed.setdefault("created", date.today().isoformat())
            routed.setdefault("title", Path(rel).stem)
            routed.setdefault("raw_text", summary_obj["raw_text"])
            rendered = render_note(cfg.templates_path, routed)
            note_path = write_note(vault, routed["type"], routed["title"], rendered)
            print(
                "REHYDRATED_EXPORT_NOTE: "
                f"{knowledge_subdir()}/Export/{rel} -> {note_path.relative_to(vault).as_posix()}"
            )
            consumed.append(rel)
            written += 1
        except Exception as e:
            print(f"REHYDRATE_EXPORT_ERROR: {rel} :: {e}")
    return written, consumed


def _known_export_files(vault: Path) -> set[str]:
    from shared.vault_layout import knowledge_subdir

    db_root = vault / knowledge_subdir()
    export_root = db_root / "Export"
    if not export_root.is_dir():
        return set()
    return {
        p.relative_to(export_root).as_posix()
        for p in export_root.rglob("*")
        if p.is_file() and not p.name.startswith(".")
    }


def _looks_like_export_ref(raw: str, rel_export: str) -> bool:
    return ("Export" in raw) or bool(re.match(r"^\d{4}/\d{2}/", rel_export))


def _export_case_map(known_files: set[str]) -> dict[str, str]:
    return {rel.lower(): rel for rel in known_files}


def _canonical_export_ref(rel_export: str, case_map: dict[str, str]) -> str | None:
    return case_map.get(rel_export.lower())


def _cleanup_broken_attachment_refs(vault: Path) -> int:
    from shared.vault_layout import knowledge_subdir

    db_root = vault / knowledge_subdir()
    if not db_root.is_dir():
        return 0
    known_files = _known_export_files(vault)
    case_map = _export_case_map(known_files)
    fm_re = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
    touched = 0
    for note in db_root.rglob("*.md"):
        if not note.is_file():
            continue
        try:
            rel = note.relative_to(db_root)
        except ValueError:
            continue
        if "Export" in rel.parts:
            continue
        text = note.read_text(encoding="utf-8", errors="ignore")
        m = fm_re.match(text)
        if not m:
            continue
        body = text[m.end() :]
        try:
            fm = yaml.safe_load(m.group(1)) or {}
        except Exception:
            continue
        if not isinstance(fm, dict):
            continue
        att = fm.get("attachments")
        if not isinstance(att, dict):
            continue
        files = att.get("files")
        if not isinstance(files, list) or not files:
            continue
        keep: list[str] = []
        changed = False
        for item in files:
            raw = str(item).strip()
            rel_export = normalize_export_ref(raw)
            looks_export = _looks_like_export_ref(raw, rel_export)
            if not (looks_export and rel_export):
                keep.append(raw)
                continue
            canonical = _canonical_export_ref(rel_export, case_map)
            if canonical and canonical != rel_export:
                changed = True
                fixed = f"{knowledge_subdir()}/Export/{canonical}"
                print(
                    "BROKEN_EXPORT_REF_CASE_FIXED: "
                    f"{note.relative_to(vault).as_posix()} :: {raw} -> {fixed}"
                )
                keep.append(fixed)
                continue
            if canonical is None:
                changed = True
                print(f"BROKEN_EXPORT_REF_REMOVED: {note.relative_to(vault).as_posix()} :: {raw}")
                continue
            keep.append(raw)
        if not changed:
            continue
        att["files"] = keep
        fm["attachments"] = att
        fm_yaml = yaml.safe_dump(fm, allow_unicode=True, sort_keys=False).strip()
        note.write_text(f"---\n{fm_yaml}\n---\n{body.lstrip()}", encoding="utf-8")
        touched += 1
    return touched


def _cleanup_broken_body_refs(vault: Path) -> int:
    from shared.vault_layout import knowledge_subdir

    db_root = vault / knowledge_subdir()
    if not db_root.is_dir():
        return 0
    known_files = _known_export_files(vault)
    case_map = _export_case_map(known_files)
    wikilink_re = re.compile(r"(!)?\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")
    touched = 0
    for note in db_root.rglob("*.md"):
        if not note.is_file():
            continue
        try:
            rel_note = note.relative_to(db_root)
        except ValueError:
            continue
        if "Export" in rel_note.parts:
            continue
        text = note.read_text(encoding="utf-8", errors="ignore")
        changed = False

        def repl(m: re.Match[str]) -> str:
            nonlocal changed
            is_embed = bool(m.group(1))
            raw = (m.group(2) or "").strip()
            alias = (m.group(3) or "").strip()
            rel_export = normalize_export_ref(raw)
            if not rel_export or not _looks_like_export_ref(raw, rel_export):
                return m.group(0)
            canonical = _canonical_export_ref(rel_export, case_map)
            if canonical == rel_export:
                return m.group(0)
            if canonical:
                changed = True
                fixed_target = f"{knowledge_subdir()}/Export/{canonical}"
                suffix = f"|{alias}" if alias else ""
                print(
                    "BROKEN_EXPORT_BODY_REF_CASE_FIXED: "
                    f"{note.relative_to(vault).as_posix()} :: {raw} -> {fixed_target}"
                )
                return f"{'!' if is_embed else ''}[[{fixed_target}{suffix}]]"
            changed = True
            print(f"BROKEN_EXPORT_BODY_REF_REMOVED: {note.relative_to(vault).as_posix()} :: {raw}")
            if is_embed:
                return ""
            return alias or Path(rel_export).stem

        new_text = wikilink_re.sub(repl, text)
        if not changed:
            continue
        note.write_text(new_text, encoding="utf-8")
        touched += 1
    return touched


def main() -> None:
    args = _parse_args()
    if args.vault:
        os.environ["VAULT_PATH"] = str(args.vault.resolve())
    cfg = load_config()
    vault = cfg.vault_path
    inv = collect_export_inventory(vault)
    orphans = sorted(rel for rel in inv.export_files if rel not in inv.referenced)
    orphan_bytes = sum(inv.export_files[rel].stat().st_size for rel in orphans)
    total_bytes = sum(p.stat().st_size for p in inv.export_files.values())

    print(
        "EXPORT_ORPHANS_SUMMARY: "
        f"total={len(orphans)} bytes={orphan_bytes} "
        f"referenced={len(inv.referenced)} export_total={len(inv.export_files)} export_bytes={total_bytes}"
    )
    print(f"EXPORT_BROKEN_REFS: count={len(inv.broken_refs)}")
    for note_rel, raw_ref in inv.broken_refs[: max(0, args.print_limit)]:
        print(f"BROKEN_EXPORT_REF: {note_rel} :: {raw_ref}")

    cleaned_notes = 0
    if args.apply and args.cleanup_broken_refs:
        cleaned_notes = _cleanup_broken_attachment_refs(vault)
        inv = collect_export_inventory(vault)
        orphans = sorted(rel for rel in inv.export_files if rel not in inv.referenced)
        print(f"EXPORT_BROKEN_REFS_CLEANED_NOTES: count={cleaned_notes}")
    body_cleaned_notes = 0
    if args.apply and args.cleanup_broken_body_refs:
        body_cleaned_notes = _cleanup_broken_body_refs(vault)
        inv = collect_export_inventory(vault)
        orphans = sorted(rel for rel in inv.export_files if rel not in inv.referenced)
        print(f"EXPORT_BROKEN_BODY_REFS_CLEANED_NOTES: count={body_cleaned_notes}")

    rehydrated = 0
    consumed: list[str] = []
    if args.apply and args.rehydrate_limit > 0:
        rehydrated, consumed = _rehydrate_orphans(
            vault=vault,
            rel_paths=orphans,
            limit=max(0, args.rehydrate_limit),
            max_mb=max(0, args.rehydrate_max_mb),
            cfg=cfg,
        )
    print(f"EXPORT_REHYDRATED_TOTAL: count={rehydrated}")

    if consumed:
        inv = collect_export_inventory(vault)
        orphans = sorted(rel for rel in inv.export_files if rel not in inv.referenced)

    if not (args.apply and args.allow_delete):
        for rel in orphans[: max(0, args.print_limit)]:
            print(f"  delete: {knowledge_subdir()}/Export/{rel}")
        print("EXPORT_ORPHANS_DELETED_TOTAL: count=0 bytes=0")
        return

    if len(orphans) > max(0, args.delete_cap):
        print(
            "EXPORT_ORPHANS_DELETE_SKIPPED_CAP: "
            f"count={len(orphans)} cap={max(0, args.delete_cap)}"
        )
        print("EXPORT_ORPHANS_DELETED_TOTAL: count=0 bytes=0")
        return

    deleted = 0
    deleted_bytes = 0
    db_root = vault / knowledge_subdir()
    for rel in orphans:
        full = db_root / "Export" / rel
        if not full.exists():
            continue
        try:
            deleted_bytes += full.stat().st_size
        except OSError:
            pass
        try:
            full.unlink()
            deleted += 1
            print(f"  deleted: {knowledge_subdir()}/Export/{rel}")
        except OSError:
            continue
    print(f"EXPORT_ORPHANS_DELETED_TOTAL: count={deleted} bytes={deleted_bytes}")


if __name__ == "__main__":
    main()
