"""Stem → config loader policy (OSS audit F06).

Catalogs must not blank on stale locals; locale schemas prefer locale examples;
structured agent YAML merges example under local.
"""
from __future__ import annotations

from typing import Callable, Literal

LoaderKind = Literal["catalog", "locale_merged", "merged", "runtime"]

# Canonical policy for config stems under config/ and config/agent/.
CONFIG_STEM_LOADERS: dict[str, LoaderKind] = {
    # UI / domain copy — example ⊕ local overlay
    "messages": "catalog",
    "domain_messages": "catalog",
    # Locale-specific schemas
    "kanban_schema": "locale_merged",
    "dashboard_templates": "locale_merged",
    # Additive structured YAML
    "ui_capabilities": "merged",
    "platform": "merged",
    "models": "merged",
    "routing": "merged",
    "memory": "merged",
    "tools": "merged",
}


def loader_kind_for_stem(stem: str) -> LoaderKind:
    key = (stem or "").strip()
    if key not in CONFIG_STEM_LOADERS:
        raise KeyError(
            f"unknown config stem {stem!r}; register in CONFIG_STEM_LOADERS "
            f"({', '.join(sorted(CONFIG_STEM_LOADERS))})"
        )
    return CONFIG_STEM_LOADERS[key]


def load_by_policy(config_dir: str, stem: str, *, locale: str | None = None) -> dict:
    """Dispatch to the loader required by CONFIG_STEM_LOADERS."""
    from shared.yaml_config import (
        load_catalog_config,
        load_locale_merged_config,
        load_merged_config,
        load_runtime_config,
    )

    kind = loader_kind_for_stem(stem)
    if kind == "catalog":
        return load_catalog_config(config_dir, stem)
    if kind == "locale_merged":
        from shared.locale import agent_locale

        return load_locale_merged_config(config_dir, stem, locale or agent_locale())
    if kind == "merged":
        return load_merged_config(config_dir, stem)
    return load_runtime_config(config_dir, stem)
