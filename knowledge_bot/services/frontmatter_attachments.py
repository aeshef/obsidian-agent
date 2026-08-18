"""Obsidian Properties cannot edit nested YAML objects — flatten attachments."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from shared.vault_layout import knowledge_subdir


def _str_list(raw: Any) -> list[str]:
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, str):
            continue
        s = item.strip()
        if s and s not in seen:
            out.append(s)
            seen.add(s)
    return out


def _from_nested(raw: Any) -> tuple[list[str], list[str]]:
    if isinstance(raw, dict):
        return _str_list(raw.get("files")), _str_list(raw.get("links"))
    if isinstance(raw, list):
        return _str_list(raw), []
    if isinstance(raw, str) and raw.strip():
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return [], []
        return _from_nested(data)
    return [], []


def attachment_files(fm: dict[str, Any] | None) -> list[str]:
    """File paths from flat `files` and/or nested `attachments.files`."""
    if not isinstance(fm, dict):
        return []
    nested_files, _ = _from_nested(fm.get("attachments"))
    top = _str_list(fm.get("files"))
    seen = set(top)
    return top + [p for p in nested_files if p not in seen]


def attachment_links(fm: dict[str, Any] | None) -> list[str]:
    """URLs from flat `links` and/or nested `attachments.links`."""
    if not isinstance(fm, dict):
        return []
    _, nested_links = _from_nested(fm.get("attachments"))
    top = _str_list(fm.get("links"))
    seen = set(top)
    return top + [u for u in nested_links if u not in seen]


def attachments_need_flatten(fm: dict[str, Any] | None) -> bool:
    if not isinstance(fm, dict):
        return False
    if "attachments" in fm:
        return True
    files = fm.get("files")
    links = fm.get("links")
    if files is not None and not isinstance(files, list):
        return True
    if links is not None and not isinstance(links, list):
        return True
    return False


def flatten_attachment_fields(fm: dict[str, Any]) -> dict[str, Any]:
    """Replace nested `attachments:` with top-level list properties Obsidian can type."""
    files = attachment_files(fm)
    links = attachment_links(fm)
    out: dict[str, Any] = {}
    emitted = False
    for key, val in fm.items():
        if key in ("attachments", "files", "links"):
            if not emitted:
                if files:
                    out["files"] = files
                if links:
                    out["links"] = links
                emitted = True
            continue
        out[key] = val
    if not emitted:
        if files:
            out["files"] = files
        if links:
            out["links"] = links
    return out


def flatten_attachments_in_vault(vault: Path, *, apply: bool = True) -> list[str]:
    """Rewrite notes whose YAML still has nested `attachments`. Return relative paths."""
    root = vault / knowledge_subdir()
    changed: list[str] = []
    if not root.is_dir():
        return changed
    for path in root.rglob("*.md"):
        if path.name.startswith("🗺️") or "Export" in path.parts:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if not text.startswith("---"):
            continue
        try:
            end = text.index("\n---", 3)
        except ValueError:
            continue
        try:
            fm = yaml.safe_load(text[3:end]) or {}
        except yaml.YAMLError:
            continue
        if not isinstance(fm, dict) or not attachments_need_flatten(fm):
            continue
        body = text[end + len("\n---") :]
        flat = flatten_attachment_fields(fm)
        dumped = (
            "---\n"
            + yaml.dump(flat, allow_unicode=True, default_flow_style=False, sort_keys=False)
            + "---"
            + body
        )
        rel = path.relative_to(vault).as_posix()
        changed.append(rel)
        if apply:
            path.write_text(dumped, encoding="utf-8")
    return changed
