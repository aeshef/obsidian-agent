"""Legacy dashboard paths cleanup (standalone files superseded by hub dashboards)."""
from __future__ import annotations

from pathlib import Path

from shared.paths import VaultPaths
from shared.vault_paths_config import folder, vault_file

LEGACY_NUTRITION_DASHBOARD_KEY = "legacy_nutrition_dashboard_md"


def _legacy_nutrition_dashboard() -> str:
    try:
        return vault_file(LEGACY_NUTRITION_DASHBOARD_KEY)
    except Exception:
        return ""


def cleanup_legacy_dashboard_files(vault_root: Path | None = None) -> list[str]:
    root = vault_root or VaultPaths().root
    actions: list[str] = []
    legacy_name = _legacy_nutrition_dashboard()
    if not legacy_name:
        return actions
    legacy = root / folder("dashboards") / legacy_name
    if legacy.is_file():
        try:
            legacy.unlink()
            actions.append(f"deleted legacy {legacy_name}")
        except OSError:
            actions.append(f"failed to delete legacy {legacy_name}")
    return actions
