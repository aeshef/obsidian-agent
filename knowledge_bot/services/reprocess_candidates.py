"""Select generic-named notes for reprocess (rules in config/reprocess.yaml)."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import yaml

_RE_SKIP = re.compile(r"(?m)^reprocess_skip:\s*true\b")


def load_reprocess_yaml(agent_config_path: Path) -> dict[str, Any]:
    p = agent_config_path / "reprocess.yaml"
    if not p.exists():
        return {}
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def file_has_reprocess_skip(path: Path) -> bool:
    try:
        head = path.read_text(encoding="utf-8", errors="ignore")[:16000]
    except OSError:
        return False
    return bool(_RE_SKIP.search(head))


def stem_sort_key(stem: str, priority: list[str]) -> tuple:
    """Lower sort tuple = higher priority in queue."""
    for i, pref in enumerate(priority):
        if stem.startswith(pref):
            return (i, stem.lower())
    return (len(priority), stem.lower())


def discover_candidate_paths(
    vault: Path,
    cfg: dict[str, Any],
    *,
    skip_if_flag: bool = True,
) -> list[Path]:
    """Notes under allowed_folders matching bad_stem_pattern (see reprocess.yaml)."""
    from shared.vault_layout import knowledge_subdir

    db_root = vault / knowledge_subdir()
    allowed = set(cfg.get("allowed_folders") or [])
    pattern = cfg.get("bad_stem_pattern") or r"^(IMG|YouTube)"
    re_bad = re.compile(pattern, re.I)
    priority: list[str] = list(cfg.get("stem_priority") or [])

    out: list[Path] = []
    if not db_root.is_dir():
        return out

    for note_path in db_root.rglob("*.md"):
        if "Export" in note_path.parts:
            continue
        try:
            rel = note_path.relative_to(db_root)
        except ValueError:
            continue
        parts = rel.parts
        if not parts or parts[0] not in allowed:
            continue
        if not re_bad.search(note_path.stem):
            continue
        if skip_if_flag and file_has_reprocess_skip(note_path):
            continue
        out.append(note_path)

    out.sort(key=lambda p: stem_sort_key(p.stem, priority))
    return out


def compile_bad_stem_regex(cfg: dict[str, Any]) -> re.Pattern[str]:
    pattern = cfg.get("bad_stem_pattern") or r"^(IMG|YouTube)"
    return re.compile(pattern, re.I)
