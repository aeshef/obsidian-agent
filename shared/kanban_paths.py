"""Kanban board file paths from vault_paths.yaml (active + optional archive)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from shared.agent.platform_config import platform_int
from shared.paths import vault_root_optional
from shared.vault_paths_config import folder, vault_file


def _vault_root() -> Path:
    root = vault_root_optional()
    if root is not None:
        return root
    from planning_bot.core.config import VAULT_PATH

    return VAULT_PATH


@lru_cache(maxsize=1)
def kanban_archive_file_configured() -> bool:
    block = __import__("shared.vault_paths_config", fromlist=["vault_paths_config"]).vault_paths_config().get(
        "files"
    ) or {}
    return bool(block.get("kanban_archive_board"))


def kanban_active_path(vault_root: Path | None = None) -> Path:
    root = vault_root or _vault_root()
    return root / folder("tasks") / vault_file("kanban_board")


def kanban_archive_path(vault_root: Path | None = None) -> Path | None:
    if not kanban_archive_file_configured():
        return None
    root = vault_root or _vault_root()
    return root / folder("tasks") / vault_file("kanban_archive_board")


def kanban_archive_enabled() -> bool:
    if not kanban_archive_file_configured():
        return False
    return platform_int("planning", "kanban_archive_enabled", default=1) != 0


def iter_kanban_read_paths(vault_root: Path | None = None) -> list[Path]:
    """Paths to read for full task corpus (active always; archive when enabled)."""
    paths = [kanban_active_path(vault_root)]
    if kanban_archive_enabled():
        archive = kanban_archive_path(vault_root)
        if archive is not None:
            paths.append(archive)
    return paths


def read_merged_kanban_text(vault_root: Path | None = None) -> str:
    parts: list[str] = []
    for path in iter_kanban_read_paths(vault_root):
        if path.is_file():
            parts.append(path.read_text(encoding="utf-8"))
    return "\n\n".join(parts)
