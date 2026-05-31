from __future__ import annotations

from pathlib import Path

from knowledge_bot.services.query.brain_query import _extract_media_from_notes


def media_from_note_text(raw: str, rel_path: str, vault_path: Path) -> list[tuple[str, str]]:
    """English docstring omitted (see domain_messages.yaml)."""
    return _extract_media_from_notes({rel_path: raw}, vault_path)


def merge_media_files(
    existing: list[tuple[str, str]],
    new_items: list[tuple[str, str]],
    *,
    max_total: int,
) -> list[tuple[str, str]]:
    seen = {a for a, _ in existing}
    out = list(existing)
    for rel, title in new_items:
        if rel in seen:
            continue
        seen.add(rel)
        out.append((rel, title))
        if len(out) >= max_total:
            break
    return out
