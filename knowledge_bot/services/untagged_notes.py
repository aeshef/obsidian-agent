"""Find knowledge notes without tags (orphans in the tag graph)."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import yaml

from knowledge_bot.services.tags_inventory import extract_tags_from_note

_FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)


def _created_day(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return ""
    match = _FM_RE.match(text)
    if match:
        fm = yaml.safe_load(match.group(1)) or {}
        created = str(fm.get("created") or "").strip()[:10]
        if created:
            return created
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d")
    except OSError:
        return ""


def find_untagged_note_paths(
    vault: Path,
    *,
    created_on: str | None = None,
    target_dirs: list[str] | None = None,
) -> list[Path]:
    """Notes with empty or missing tags (skips hub pages 🗺️)."""
    from shared.vault_layout import knowledge_subdir

    dirs = target_dirs or [knowledge_subdir()]
    out: list[Path] = []
    for d in dirs:
        root = vault / d
        if not root.is_dir():
            continue
        for md in root.rglob("*.md"):
            if "Export" in md.parts:
                continue
            if md.name.startswith("🗺️"):
                continue
            if extract_tags_from_note(md):
                continue
            if created_on and _created_day(md) != created_on:
                continue
            out.append(md)
    out.sort(key=lambda p: p.stat().st_mtime)
    return out


def count_untagged_notes(vault: Path) -> int:
    return len(find_untagged_note_paths(vault))
