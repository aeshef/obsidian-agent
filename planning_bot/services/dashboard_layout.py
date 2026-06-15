"""Legacy dashboard paths cleanup (standalone files superseded by hub dashboards)."""
from __future__ import annotations

from pathlib import Path

from shared.paths import VaultPaths
from shared.vault_paths_config import folder

# Superseded by health_dashboard_md (🏥 Здоровье.md); kept for sync cleanup only.
LEGACY_NUTRITION_DASHBOARD = "🥗 Питание_КБЖУ.md"


def cleanup_legacy_dashboard_files(vault_root: Path | None = None) -> list[str]:
    root = vault_root or VaultPaths().root
    actions: list[str] = []
    legacy = root / folder("dashboards") / LEGACY_NUTRITION_DASHBOARD
    if legacy.is_file():
        try:
            legacy.unlink()
            actions.append(f"deleted legacy {LEGACY_NUTRITION_DASHBOARD}")
        except OSError:
            actions.append(f"failed to delete legacy {LEGACY_NUTRITION_DASHBOARD}")
    return actions
