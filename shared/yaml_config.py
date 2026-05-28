"""YAML config loading (shared by all bots)."""
from __future__ import annotations

import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger("shared.yaml")


def load_yaml(path: Path, *, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return dict(default or {})
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else dict(default or {})
    except Exception as e:
        log.error("Failed to load YAML %s: %s", path, e, exc_info=True)
        return dict(default or {})


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, val in override.items():
        if key in out and isinstance(out[key], dict) and isinstance(val, dict):
            out[key] = deep_merge(out[key], val)
        else:
            out[key] = val
    return out


@lru_cache(maxsize=32)
def load_yaml_cached(path_str: str) -> dict[str, Any]:
    return load_yaml(Path(path_str))


@lru_cache(maxsize=32)
def load_merged_config(config_dir: str, stem: str) -> dict[str, Any]:
    """Merge {stem}.yaml over {stem}.yaml.example (example is in git)."""
    base = Path(config_dir)
    example = base / f"{stem}.yaml.example"
    merged = load_yaml(example, default={}) if example.is_file() else {}
    local = base / f"{stem}.yaml"
    if local.is_file():
        over = load_yaml(local, default={})
        if over:
            merged = deep_merge(merged, over)
    return merged


@lru_cache(maxsize=32)
def load_runtime_config(config_dir: str, stem: str) -> dict[str, Any]:
    """Production config: local yaml only when present; else example (first-run OSS).

    Unlike load_merged_config, never deep-merges example under an existing local file.
    """
    base = Path(config_dir)
    local = base / f"{stem}.yaml"
    if local.is_file():
        return load_yaml(local, default={})
    example = base / f"{stem}.yaml.example"
    if example.is_file():
        return load_yaml(example, default={})
    return {}


def load_yaml_list_runtime(config_dir: str, stem: str) -> list[str]:
    """YAML list config: local {stem}.yaml else {stem}.yaml.example (OSS first-run)."""
    base = Path(config_dir)
    for name in (f"{stem}.yaml", f"{stem}.yaml.example"):
        path = base / name
        if not path.is_file():
            continue
        try:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
        except Exception as e:
            log.error("Failed to load YAML list %s: %s", path, e, exc_info=True)
            continue
        if isinstance(data, list) and data:
            return [str(x) for x in data]
    return []


def clear_runtime_config_cache() -> None:
    load_merged_config.cache_clear()
    load_runtime_config.cache_clear()
    load_yaml_cached.cache_clear()
