"""Detect default locale vault_paths stubs (onboarding reset)."""
from __future__ import annotations

import shutil
from functools import lru_cache
from pathlib import Path
from typing import Any

from shared.yaml_config import load_yaml

_REPO = Path(__file__).resolve().parents[2]
_FOLDER_KEYS = ("tasks", "goals", "dashboards", "routines", "handwritten")


@lru_cache(maxsize=2)
def _default_folders(locale: str) -> dict[str, str]:
    name = (
        "vault_paths.ru.yaml.example"
        if (locale or "").strip().lower().startswith("ru")
        else "vault_paths.en.yaml.example"
    )
    doc = load_yaml(_REPO / "config" / name, default={}) or {}
    folders = doc.get("folders")
    if not isinstance(folders, dict):
        return {}
    return {k: str(folders[k]) for k in _FOLDER_KEYS if k in folders}


def _folders_match(doc: dict[str, Any], expected: dict[str, str]) -> bool:
    folders = doc.get("folders")
    if not isinstance(folders, dict):
        return False
    return all(folders.get(k) == v for k, v in expected.items())


def is_default_en_vault_paths(doc: dict[str, Any]) -> bool:
    return _folders_match(doc, _default_folders("en"))


def is_default_ru_vault_paths(doc: dict[str, Any]) -> bool:
    return _folders_match(doc, _default_folders("ru"))


def should_replace_vault_paths_for_locale(doc: dict[str, Any], locale: str) -> bool:
    """True when vault_paths is still the other locale's default (fresh wrong-locale copy)."""
    loc = (locale or "en").strip().lower()
    if loc.startswith("ru"):
        return is_default_en_vault_paths(doc)
    return is_default_ru_vault_paths(doc)


def ghost_folder_segments(locale: str | None = None) -> list[str]:
    """Top-level vault folder names from the *other* locale (empty ghosts to remove)."""
    from shared.locale import agent_locale

    loc = (locale or agent_locale() or "en").strip().lower()
    other = "en" if loc.startswith("ru") else "ru"
    folders = _default_folders(other)
    return [folders[k] for k in _FOLDER_KEYS if k in folders]


def cleanup_ghost_locale_folders(vault_root: Path, *, locale: str | None = None) -> list[str]:
    """Remove empty wrong-locale top-level folders (idempotent)."""
    actions: list[str] = []
    root = Path(vault_root)
    if not root.is_dir():
        return actions
    for name in ghost_folder_segments(locale):
        path = root / name
        if not path.is_dir():
            continue
        if any(p.is_file() for p in path.rglob("*")):
            continue
        try:
            shutil.rmtree(path)
            actions.append(f"removed ghost folder {name}")
        except OSError:
            continue
    return actions
