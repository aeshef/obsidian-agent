"""Migrate and scaffold 400_Routines vault layout (idempotent)."""
from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from planning_bot.services.routines_config import section_config_header
from shared.routines_paths import (
    routines_charts_dir,
    routines_data_dir,
    routines_operational_dir,
    routines_stats_legacy_path,
    routines_stats_path,
    routines_today_json_path,
    routines_today_legacy_path,
    signals_dir,
    signals_history_path,
)
from shared.vault_paths_config import routines_sub


def _mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)


def _migrate_today_md_to_json(vault_root: Path | None = None) -> bool:
    legacy = routines_today_legacy_path(vault_root)
    json_path = routines_today_json_path(vault_root)
    if not legacy.is_file():
        return False
    if json_path.is_file():
        try:
            legacy.unlink()
            return True
        except OSError:
            return False
    content = legacy.read_text(encoding="utf-8")
    date_match = re.search(r"\*\*Дата:\*\*\s*(\d{4}-\d{2}-\d{2})", content)
    if not date_match:
        date_match = re.search(r"\*\*Date:\*\*\s*(\d{4}-\d{2}-\d{2})", content)
    day = date_match.group(1) if date_match else ""
    status: dict[str, dict[str, bool]] = {"morning": {}, "day": {}, "evening": {}}
    current_section: str | None = None
    for line in content.split("\n"):
        for section in ("morning", "day", "evening"):
            if section_config_header(section) in line:
                current_section = section
                break
        else:
            if current_section and line.strip().startswith("- ["):
                match = re.match(r"-\s*\[([ x])\]\s*(.+)", line.strip())
                if match:
                    status[current_section][match.group(2).strip()] = match.group(1) == "x"
    payload = {
        "date": day,
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
    }
    _mkdir(json_path.parent)
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    try:
        legacy.unlink()
    except OSError:
        pass
    return True


def _move_stats_if_needed(
    new_path: Path,
    legacy_path: Path | None,
) -> bool:
    if new_path.is_file():
        return False
    if legacy_path is None or not legacy_path.is_file():
        return False
    _mkdir(new_path.parent)
    shutil.move(str(legacy_path), str(new_path))
    return True


def cleanup_legacy_routines_files(vault_root: Path | None = None) -> list[str]:
    """Remove deprecated paths so rsync --update cannot resurrect them locally."""
    actions: list[str] = []
    for path in (routines_stats_legacy_path(vault_root), routines_today_legacy_path(vault_root)):
        if path is not None and path.is_file():
            try:
                path.unlink()
                actions.append(f"deleted legacy {path.name}")
            except OSError:
                actions.append(f"failed to delete legacy {path.name}")
    return actions


def ensure_routines_layout(vault_root: Path | None = None, *, scaffold_stats: bool = True) -> list[str]:
    """Create dirs, migrate legacy paths, scaffold stats pages. Returns action log."""
    actions: list[str] = []
    actions.extend(cleanup_legacy_routines_files(vault_root))
    _mkdir(routines_operational_dir(vault_root))
    _mkdir(routines_data_dir(vault_root))
    _mkdir(routines_charts_dir(vault_root) / routines_sub("charts_routines"))
    _mkdir(routines_charts_dir(vault_root) / routines_sub("charts_signals"))
    _mkdir(signals_dir(vault_root))

    if _migrate_today_md_to_json(vault_root):
        actions.append("migrated today markdown → routines_today.json")

    legacy_stats = routines_stats_legacy_path(vault_root)
    if _move_stats_if_needed(routines_stats_path(vault_root), legacy_stats):
        actions.append(f"moved routines stats → {routines_stats_path(vault_root).name}")

    hist = signals_history_path(vault_root)
    if not hist.is_file():
        from planning_bot.app.ui import pmsg

        hist.write_text(pmsg("checkin_signals_history_header") + "\n", encoding="utf-8")
        actions.append("created signals history")

    if scaffold_stats:
        from shared.capabilities.vault_routines_scaffold import scaffold_vault_routines

        for path in scaffold_vault_routines(vault_root=vault_root):
            actions.append(f"scaffold: {path}")

    return actions


def migrate_routines_layout(vault_root: Path | None = None) -> list[str]:
    return ensure_routines_layout(vault_root, scaffold_stats=True)
