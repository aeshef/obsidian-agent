"""Paths and atomic promote for goals task mapping (staging vs production)."""
from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Dict, Optional

STAGING_BASENAME = "goals_task_mapping.staging.json"
IN_PROGRESS_MARKER = "goals_mapping_remap_in_progress"


def resolve_mapping_file(default: Path) -> Path:
    override = os.environ.get("GOALS_MAPPING_FILE", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return default


def staging_mapping_file(vault_path: Path) -> Path:
    return vault_path / ".sync" / STAGING_BASENAME


def remap_in_progress_marker(vault_path: Path) -> Path:
    return vault_path / ".sync" / IN_PROGRESS_MARKER


def write_json_atomic(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def promote_mapping_file(staging: Path, production: Path) -> None:
    """Atomically replace production mapping with a completed staging file."""
    if not staging.is_file():
        raise FileNotFoundError(f"staging mapping not found: {staging}")
    production.parent.mkdir(parents=True, exist_ok=True)
    tmp = production.with_name(production.name + ".tmp")
    shutil.copy2(staging, tmp)
    os.replace(tmp, production)


def touch_remap_in_progress(vault_path: Path, *, staging: Path, production: Path) -> Path:
    marker = remap_in_progress_marker(vault_path)
    write_json_atomic(
        marker,
        {
            "staging": str(staging),
            "production": str(production),
            "status": "in_progress",
        },
    )
    return marker


def clear_remap_in_progress(vault_path: Path) -> None:
    marker = remap_in_progress_marker(vault_path)
    if marker.is_file():
        marker.unlink()


def load_mapping_titles(path: Path) -> Dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    titles = data.get("task_titles")
    return dict(titles) if isinstance(titles, dict) else {}
