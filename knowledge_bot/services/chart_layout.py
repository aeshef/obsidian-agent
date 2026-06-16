"""Legacy vault chart paths cleanup."""
from __future__ import annotations

from pathlib import Path

from shared.paths import VaultPaths

from knowledge_bot.services.maintenance_metrics import (
    cleanup_legacy_maintenance_chart,
    _legacy_maintenance_chart_name,
)


def cleanup_legacy_vault_charts(vault_root: Path | None = None) -> list[str]:
    root = vault_root or VaultPaths().root
    actions: list[str] = []
    if cleanup_legacy_maintenance_chart(root):
        actions.append(f"deleted legacy {_legacy_maintenance_chart_name()}")
    return actions
