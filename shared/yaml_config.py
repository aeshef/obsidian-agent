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
    Prefer load_catalog_config for UI/domain string catalogs (stale locals must not blank new keys).
    """
    base = Path(config_dir)
    local = base / f"{stem}.yaml"
    if local.is_file():
        return load_yaml(local, default={})
    example = base / f"{stem}.yaml.example"
    if example.is_file():
        return load_yaml(example, default={})
    return {}


@lru_cache(maxsize=32)
def load_catalog_config(config_dir: str, stem: str) -> dict[str, Any]:
    """String/catalog YAML: git example as schema, local overlay wins on overlap.

    Use for messages.*, domain_messages.*, and similar copy catalogs where a stale
    gitignored snapshot must not drop keys added to *.example after an upgrade.
    """
    return load_merged_config(config_dir, stem)


@lru_cache(maxsize=32)
def load_locale_merged_config(
    config_dir: str,
    stem: str,
    locale: str,
) -> dict[str, Any]:
    """Merge locale-specific example (preferred), else generic example, then local yaml.

    Prefer ``{stem}.{locale}.yaml.example`` alone when present so EN installs do not
    inherit RU labels from a Russian generic ``{stem}.yaml.example``.
    """
    base = Path(config_dir)
    loc = "ru" if str(locale).strip().lower().startswith("ru") else "en"
    loc_ex = base / f"{stem}.{loc}.yaml.example"
    generic_ex = base / f"{stem}.yaml.example"
    if loc_ex.is_file():
        merged = load_yaml(loc_ex, default={})
    elif generic_ex.is_file():
        merged = load_yaml(generic_ex, default={})
    else:
        merged = {}
    local = base / f"{stem}.yaml"
    if local.is_file():
        over = load_yaml(local, default={})
        if over:
            merged = deep_merge(merged, over)
    return merged


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
    load_catalog_config.cache_clear()
    load_locale_merged_config.cache_clear()
    load_yaml_cached.cache_clear()
