"""Routines and signals vault paths from vault_paths.yaml."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from shared.paths import vault_root_optional
from shared.vault_paths_config import folder, routines_sub, vault_file


def _vault_root() -> Path:
    root = vault_root_optional()
    if root is not None:
        return root
    raise RuntimeError("VAULT_PATH is not configured (set env or vault_paths.yaml)")


def routines_root(vault_root: Path | None = None) -> Path:
    return (vault_root or _vault_root()) / folder("routines")


def routines_operational_dir(vault_root: Path | None = None) -> Path:
    sub = vault_file("routines_calendar_subdir").rstrip("/")
    return routines_root(vault_root) / sub


def routines_data_dir(vault_root: Path | None = None) -> Path:
    return routines_root(vault_root) / routines_sub("data")


def routines_charts_dir(vault_root: Path | None = None) -> Path:
    return routines_root(vault_root) / routines_sub("charts")


def signals_dir(vault_root: Path | None = None) -> Path:
    sub = vault_file("signals_subdir").rstrip("/")
    return routines_root(vault_root) / sub


def routines_config_path(vault_root: Path | None = None) -> Path:
    return routines_operational_dir(vault_root) / vault_file("routines_config_md")


def routines_history_path(vault_root: Path | None = None) -> Path:
    return routines_operational_dir(vault_root) / vault_file("routines_history_md")


def routines_today_json_path(vault_root: Path | None = None) -> Path:
    return routines_data_dir(vault_root) / vault_file("routines_today_json")


def routines_today_legacy_path(vault_root: Path | None = None) -> Path:
    return routines_operational_dir(vault_root) / vault_file("routines_today_legacy_md")


def routines_stats_path(vault_root: Path | None = None) -> Path:
    return routines_root(vault_root) / vault_file("routines_stats_md")


def routines_stats_legacy_path(vault_root: Path | None = None) -> Path | None:
    block = __import__(
        "shared.vault_paths_config", fromlist=["vault_paths_config"]
    ).vault_paths_config().get("files") or {}
    legacy = block.get("routines_stats_legacy_md")
    if not legacy:
        return None
    return routines_root(vault_root) / str(legacy)


def signals_history_path(vault_root: Path | None = None) -> Path:
    return signals_dir(vault_root) / vault_file("signals_history_md")


def signals_config_md_path(vault_root: Path | None = None) -> Path:
    return signals_dir(vault_root) / vault_file("signals_config_md")


def signals_config_yaml_legacy_path(vault_root: Path | None = None) -> Path | None:
    block = __import__(
        "shared.vault_paths_config", fromlist=["vault_paths_config"]
    ).vault_paths_config().get("files") or {}
    legacy = block.get("signals_config_yaml")
    if not legacy:
        return None
    return signals_dir(vault_root) / str(legacy)


def signals_config_path(vault_root: Path | None = None) -> Path:
    """Editable signals config (markdown with YAML block)."""
    return signals_config_md_path(vault_root)


@lru_cache(maxsize=1)
def signals_config_wikilink() -> str:
    sub = vault_file("signals_subdir").rstrip("/")
    name = vault_file("signals_config_md")
    rel = f"{folder('routines')}/{sub}/{name}"
    return rel.replace(".md", "")


def signals_stats_path(vault_root: Path | None = None) -> Path:
    return routines_root(vault_root) / vault_file("signals_stats_md")


@lru_cache(maxsize=1)
def routines_stats_wikilink() -> str:
    """Vault-relative path without extension for dataview wikilinks."""
    rel = f"{folder('routines')}/{vault_file('routines_stats_md')}"
    return rel.replace(".md", "")


@lru_cache(maxsize=1)
def signals_stats_wikilink() -> str:
    rel = f"{folder('routines')}/{vault_file('signals_stats_md')}"
    return rel.replace(".md", "")


@lru_cache(maxsize=1)
def routines_history_wikilink() -> str:
    op = vault_file("routines_calendar_subdir").rstrip("/")
    hist = vault_file("routines_history_md")
    rel = f"{folder('routines')}/{op}/{hist}"
    return rel.replace(".md", "")


@lru_cache(maxsize=1)
def routines_config_wikilink() -> str:
    op = vault_file("routines_calendar_subdir").rstrip("/")
    cfg = vault_file("routines_config_md")
    rel = f"{folder('routines')}/{op}/{cfg}"
    return rel.replace(".md", "")


@lru_cache(maxsize=1)
def signals_history_wikilink() -> str:
    sub = vault_file("signals_subdir").rstrip("/")
    hist = vault_file("signals_history_md")
    rel = f"{folder('routines')}/{sub}/{hist}"
    return rel.replace(".md", "")
