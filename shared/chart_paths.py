"""Resolve dashboard chart paths from config/vault_paths.yaml."""
from __future__ import annotations

from pathlib import Path

from shared.vault_paths_config import dashboards_sub, folder, vault_file, vault_rel_path


def charts_root(vault: Path) -> Path:
    return vault / folder("dashboards") / dashboards_sub("charts")


def chart_path(vault: Path, key: str, **fmt: object) -> Path:
    rel = vault_file(key, **fmt)
    return charts_root(vault) / rel


def data_path(vault: Path, key: str) -> Path:
    return vault / folder("dashboards") / dashboards_sub("data") / vault_rel_path(key)


def ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


def chart_wikilink_png(file_key: str) -> str:
    """Obsidian embed for chart PNG — always .png to avoid md self-embed loops."""
    rel = vault_file(file_key)
    if not rel.lower().endswith(".png"):
        rel = f"{rel}.png"
    return f"![[{dashboards_sub('charts')}/{rel}]]"
