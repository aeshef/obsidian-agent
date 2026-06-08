"""Detect default locale vault_paths stubs (onboarding reset)."""
from __future__ import annotations

from typing import Any

# Folder keys compared when switching locale on a pristine install.
_FOLDER_KEYS = ("tasks", "goals", "dashboards", "routines", "handwritten")

_DEFAULT_EN_FOLDERS: dict[str, str] = {
    "tasks": "100_Tasks",
    "goals": "200_Goals",
    "dashboards": "300_Dashboards",
    "routines": "400_Routines",
    "handwritten": "600_Handwritten",
}

_DEFAULT_RU_FOLDERS: dict[str, str] = {
    "tasks": "100_Задачи",
    "goals": "200_Цели",
    "dashboards": "300_Дашборды",
    "routines": "400_Рутины",
    "handwritten": "600_Рукописное",
}


def _folders_match(doc: dict[str, Any], expected: dict[str, str]) -> bool:
    folders = doc.get("folders")
    if not isinstance(folders, dict):
        return False
    return all(folders.get(k) == v for k, v in expected.items())


def is_default_en_vault_paths(doc: dict[str, Any]) -> bool:
    return _folders_match(doc, _DEFAULT_EN_FOLDERS)


def is_default_ru_vault_paths(doc: dict[str, Any]) -> bool:
    return _folders_match(doc, _DEFAULT_RU_FOLDERS)


def should_replace_vault_paths_for_locale(doc: dict[str, Any], locale: str) -> bool:
    """True when vault_paths is still the other locale's default (fresh wrong-locale copy)."""
    loc = (locale or "en").strip().lower()
    if loc.startswith("ru"):
        return is_default_en_vault_paths(doc)
    return is_default_ru_vault_paths(doc)
