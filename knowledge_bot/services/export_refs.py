"""Export file reference index helpers (frontmatter + body wikilinks)."""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

from knowledge_bot.services.frontmatter_attachments import attachment_files
from shared.vault_layout import knowledge_subdir

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_WIKILINK_RE = re.compile(
    r"!\[\[([^\]|]+)(?:\|[^\]]+)?\]\]|\[\[([^\]|]+)(?:\|[^\]]+)?\]\]"
)


@dataclass(frozen=True)
class ExportInventory:
    export_root: Path
    export_files: dict[str, Path]
    referenced: set[str]
    broken_refs: list[tuple[str, str]]


def normalize_export_ref(raw_ref: str) -> str:
    """Normalize note reference to Export-relative path (`YYYY/MM/file.ext`)."""
    ref = (raw_ref or "").strip().replace("\\", "/").lstrip("/")
    if not ref:
        return ""
    try:
        db_export_prefix = f"{knowledge_subdir().strip('/')}/Export/"
    except Exception:
        db_export_prefix = ""
    for prefix in (db_export_prefix, "Export/"):
        if ref.startswith(prefix):
            ref = ref[len(prefix) :]
    if "Export/" in ref:
        ref = ref.split("Export/", 1)[1]
    if "#" in ref:
        ref = ref.split("#", 1)[0]
    return ref.strip()


def resolve_export_ref(ref: str, export_files: dict[str, Path]) -> str | None:
    """Resolve an Export-relative ref to actual on-disk casing when possible."""
    if ref in export_files:
        return ref
    lower_ref = ref.lower()
    for existing in export_files:
        if existing.lower() == lower_ref:
            return existing
    return None


def _parse_frontmatter_and_body(note_path: Path) -> tuple[dict, str]:
    text = note_path.read_text(encoding="utf-8", errors="ignore")
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    body = text[m.end() :]
    try:
        fm = yaml.safe_load(m.group(1)) or {}
    except Exception:
        fm = {}
    return (fm if isinstance(fm, dict) else {}), body


def _iter_db_notes(vault: Path):
    db_root = vault / knowledge_subdir()
    if not db_root.is_dir():
        return
    for note in db_root.rglob("*.md"):
        if not note.is_file():
            continue
        try:
            rel = note.relative_to(db_root)
        except ValueError:
            continue
        if "Export" in rel.parts:
            continue
        yield note


def collect_export_inventory(vault: Path) -> ExportInventory:
    db_root = vault / knowledge_subdir()
    export_root = db_root / "Export"
    export_files = {
        p.relative_to(export_root).as_posix(): p
        for p in export_root.rglob("*")
        if p.is_file() and not p.name.startswith(".")
    }
    export_case_map = {rel.lower(): rel for rel in export_files}
    referenced: set[str] = set()
    broken_refs: list[tuple[str, str]] = []
    broken_seen: set[tuple[str, str]] = set()

    def resolve_local(ref: str) -> str | None:
        if ref in export_files:
            return ref
        return export_case_map.get(ref.lower())

    for note in _iter_db_notes(vault):
        fm, body = _parse_frontmatter_and_body(note)
        note_rel = note.relative_to(vault).as_posix()
        files = attachment_files(fm) if isinstance(fm, dict) else []
        for path_like in files:
            ref = normalize_export_ref(str(path_like))
            if not ref:
                continue
            resolved = resolve_local(ref)
            if resolved:
                referenced.add(resolved)
            elif "Export" in str(path_like) or re.match(r"^\d{4}/\d{2}/", ref):
                item = (note_rel, str(path_like))
                if item not in broken_seen:
                    broken_seen.add(item)
                    broken_refs.append(item)
        for m in _WIKILINK_RE.finditer(body):
            for g in m.groups():
                if not g:
                    continue
                ref = normalize_export_ref(g.strip())
                if not ref:
                    continue
                resolved = resolve_local(ref)
                if resolved:
                    referenced.add(resolved)
                elif "Export" in g or re.match(r"^\d{4}/\d{2}/", ref):
                    item = (note_rel, g.strip())
                    if item not in broken_seen:
                        broken_seen.add(item)
                        broken_refs.append(item)
    return ExportInventory(
        export_root=export_root,
        export_files=export_files,
        referenced=referenced,
        broken_refs=broken_refs,
    )


def collect_orphan_export_files(vault: Path) -> list[str]:
    inv = collect_export_inventory(vault)
    return sorted(rel for rel in inv.export_files.keys() if rel not in inv.referenced)
