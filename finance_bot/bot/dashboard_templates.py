"""Dashboard markdown templates from finance_bot/config/dashboard_templates.yaml."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from shared.yaml_config import load_merged_config

_CONFIG = Path(__file__).resolve().parent.parent / "config"


@lru_cache(maxsize=1)
def _templates() -> dict:
    return load_merged_config(str(_CONFIG), "dashboard_templates")


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
