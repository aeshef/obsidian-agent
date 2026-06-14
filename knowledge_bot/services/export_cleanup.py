"""Safe cleanup for unreferenced Export files."""
from __future__ import annotations

from pathlib import Path

from knowledge_bot.services.export_refs import collect_export_inventory, normalize_export_ref


def cleanup_unreferenced_export_files(
    vault: Path, candidate_refs: list[str]
) -> list[str]:
    """Delete only candidate Export files that are currently unreferenced."""
    inv = collect_export_inventory(vault)
    deleted: list[str] = []
    seen: set[str] = set()
    for raw in candidate_refs:
        rel = normalize_export_ref(str(raw))
        if not rel or rel in seen:
            continue
        seen.add(rel)
        if rel in inv.referenced:
            continue
        full = inv.export_files.get(rel)
        if full is None or not full.exists():
            continue
        try:
            full.unlink()
            deleted.append(rel)
        except OSError:
            continue
    return deleted
