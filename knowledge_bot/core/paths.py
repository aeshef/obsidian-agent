"""Unified vault paths for all bots. Folder names live in config/vault_paths.yaml."""
from __future__ import annotations

import os
from pathlib import Path

from shared.vault_paths_config import dashboards_sub, folder


def vault_root_optional() -> Path | None:
    """Vault root from VAULT_PATH / OBSIDIAN_VAULT_PATH (no home-dir guessing)."""
    raw = os.environ.get("VAULT_PATH") or os.environ.get("OBSIDIAN_VAULT_PATH")
    if not raw:
        return None
    p = Path(raw).expanduser().resolve()
    return p if p.is_dir() else None


def vault_root() -> Path:
    p = vault_root_optional()
    if p is None:
        raise RuntimeError(
            "VAULT_PATH is not set: set VAULT_PATH or OBSIDIAN_VAULT_PATH in .env"
        )
    return p


class VaultPaths:
    """Vault topology; segment names come from config/vault_paths.yaml."""

    def __init__(self, root: Path | str | None = None):
        self.root = Path(root) if root is not None else vault_root()

    @property
    def tasks(self) -> Path:
        return self.root / folder("tasks")

    @property
    def goals(self) -> Path:
        return self.root / folder("goals")

    @property
    def dashboards(self) -> Path:
        return self.root / folder("dashboards")

    @property
    def routines(self) -> Path:
        return self.root / folder("routines")

    @property
    def handwritten(self) -> Path:
        return self.root / folder("handwritten")

    @property
    def knowledge_db(self) -> Path:
        from shared.vault_layout import knowledge_subdir

        return self.root / knowledge_subdir()

    @property
    def agent(self) -> Path:
        return self.root / folder("automation") / "Agent"

    @property
    def sync_dir(self) -> Path:
        return self.root / ".sync"

    @property
    def logs_dir(self) -> Path:
        return self.dashboards / dashboards_sub("logs")

    @property
    def charts_dir(self) -> Path:
        return self.dashboards / dashboards_sub("charts")

    @property
    def data_dir(self) -> Path:
        return self.dashboards / dashboards_sub("data")


def knowledge_db_root(vault_root_path: Path) -> Path:
    from shared.vault_layout import knowledge_subdir

    return vault_root_path / knowledge_subdir()


def target_note_path(vault_root_path: Path, type_name: str, slug: str) -> Path:
    from knowledge_bot.core.config import load_config
    from knowledge_bot.core.settings import load_types_config

    cfg = load_config()
    types = load_types_config(cfg.agent_config_path)
    subdir = types.dir_for(type_name) or types.dir_for(types.default_type) or "Знания"
    return knowledge_db_root(vault_root_path) / subdir / f"{slug}.md"


def build_export_path(export_root: Path, filename: str, h8: str) -> Path:
    from datetime import date

    safe = Path(filename).name.replace(" ", "_")
    today = date.today()
    return export_root / str(today.year) / f"{today.month:02d}" / f"{h8}_{safe}"


def build_attachments_path(attachments_root: Path, filename: str, h8: str) -> Path:
    safe = Path(filename).name.replace(" ", "_")
    return attachments_root / f"{h8}_{safe}"
