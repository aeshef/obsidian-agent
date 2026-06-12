"""Vault path segments from config/vault_paths.yaml (not hardcoded in Python)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from shared.locale import agent_locale
from shared.yaml_config import load_merged_config, load_runtime_config, load_yaml

_REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


def _check_segment(name: str, val: str, key: str) -> str:
    if not val or val.startswith("/") or ".." in val or "/" in val or "\\" in val:
        raise ValueError(f"vault_paths invalid segment {key}={val!r} (must be single folder name)")
    return val


def _vault_paths_stem() -> str:
    loc = agent_locale().strip().lower()
    return "vault_paths.en" if loc.startswith("en") else "vault_paths.ru"


@lru_cache(maxsize=2)
def vault_paths_config() -> dict:
    """Local vault_paths.yaml wins; else locale example; else generic example."""
    local = _REPO_CONFIG / "vault_paths.yaml"
    if local.is_file():
        cfg = load_yaml(local, default={})
        if cfg:
            return cfg
    stem = _vault_paths_stem()
    cfg = load_runtime_config(str(_REPO_CONFIG), stem)
    if cfg:
        return cfg
    return load_merged_config(str(_REPO_CONFIG), "vault_paths")


def folder(key: str) -> str:
    folders = vault_paths_config().get("folders") or {}
    val = folders.get(key)
    if not val:
        raise KeyError(f"vault_paths.folders.{key} missing in config/vault_paths.yaml")
    return _check_segment(key, str(val), f"folders.{key}")


def dashboards_sub(key: str) -> str:
    block = vault_paths_config().get("dashboards") or {}
    val = block.get(key)
    if not val:
        raise KeyError(f"vault_paths.dashboards.{key} missing")
    return _check_segment(key, str(val), f"dashboards.{key}")


def vault_file(key: str, **fmt: object) -> str:
    block = vault_paths_config().get("files") or {}
    template = block.get(key)
    if not template:
        raise KeyError(f"vault_paths.files.{key} missing")
    return str(template).format(**fmt)


def vault_rel_path(key: str) -> str:
    block = vault_paths_config().get("paths") or {}
    val = block.get(key)
    if not val:
        raise KeyError(f"vault_paths.paths.{key} missing")
    return str(val)


def finance_sub(key: str) -> str:
    block = vault_paths_config().get("finance") or {}
    val = block.get(key)
    if not val:
        raise KeyError(f"vault_paths.finance.{key} missing")
    return str(val)


def _domain_sub(block_name: str, key: str) -> str:
    block = vault_paths_config().get(block_name) or {}
    val = block.get(key)
    if not val:
        raise KeyError(f"vault_paths.{block_name}.{key} missing")
    return str(val)


def planning_sub(key: str) -> str:
    return _domain_sub("planning", key)


def health_sub(key: str) -> str:
    return _domain_sub("health", key)


def cross_sub(key: str) -> str:
    return _domain_sub("cross", key)


def dashboard_file(key: str, *, legacy_key: str | None = None, **fmt: object) -> str:
    """Resolve files.* with optional fallback for renamed keys."""
    block = vault_paths_config().get("files") or {}
    template = block.get(key)
    if not template and legacy_key:
        template = block.get(legacy_key)
    if not template:
        raise KeyError(f"vault_paths.files.{key} missing")
    return str(template).format(**fmt)
