"""Dashboard markdown templates from finance_bot/config/dashboard_templates.yaml."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from shared.locale import agent_locale
from shared.yaml_config import load_locale_merged_config, load_yaml

_CONFIG = Path(__file__).resolve().parent.parent / "config"


def _config_dir() -> Path:
    override = os.environ.get("FINANCE_CONFIG_DIR", "").strip()
    if override:
        return Path(override)
    return _CONFIG


@lru_cache(maxsize=1)
def _templates() -> dict:
    cfg = _config_dir()
    if os.environ.get("FINANCE_CONFIG_DIR", "").strip():
        local = cfg / "dashboard_templates.yaml"
        if local.is_file():
            return load_yaml(local, default={})
    return load_locale_merged_config(str(cfg), "dashboard_templates", agent_locale())


def dtpl_raw(*keys: str):
    """Return raw YAML node (list/dict/str) for dashboard templates."""
    node: object = _templates()
    for k in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(k)
    return node


def dtpl(*keys: str, default: str = "", **kwargs: object) -> str:
    node: object = _templates()
    for k in keys:
        if not isinstance(node, dict):
            return default
        node = node.get(k)
    template = str(node).strip() if node is not None else default
    if kwargs and template:
        try:
            return template.format(**kwargs)
        except (KeyError, ValueError):
            return template
    return template
