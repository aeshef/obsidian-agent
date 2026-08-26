"""Non-UI domain strings (tool output, lookup reasons) — config/domain_messages.{locale}.yaml."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from shared.capabilities.ui_bindings import message_allowed
from shared.locale import agent_locale
from shared.yaml_config import deep_merge, load_runtime_config, load_yaml

_REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


@lru_cache(maxsize=2)
def _domain_for_stem(stem: str) -> dict:
    return load_runtime_config(str(_REPO_CONFIG), stem)


def _overlay_yaml(merged: dict, path: Path) -> dict:
    if not path.is_file():
        return merged
    over = load_yaml(path)
    return deep_merge(merged, over) if over else merged


def _ru_domain() -> dict:
    """RU catalog: .ru.example as base, then legacy yaml, then gitignored .ru.yaml.

    Local files still win on overlapping keys (personal overrides). Missing keys
    fill from the git example so a stale prod snapshot cannot blank new copy
    (e.g. goals mapping review headings).
    """
    base = _REPO_CONFIG
    merged = load_yaml(base / "domain_messages.ru.yaml.example", default={})
    merged = _overlay_yaml(merged, base / "domain_messages.yaml")
    return _overlay_yaml(merged, base / "domain_messages.ru.yaml")


@lru_cache(maxsize=2)
def _domain(_locale: str) -> dict:
    if _locale.startswith("en"):
        ru = _ru_domain()
        en = _domain_for_stem("domain_messages.en")
        if ru and en:
            return deep_merge(ru, en)
        return en or ru
    return _ru_domain()


def _active_domain() -> dict:
    return _domain(agent_locale())


def clear_domain_messages_cache() -> None:
    _domain.cache_clear()
    _domain_for_stem.cache_clear()


def dmsg(*keys: str, default: str = "", cap: str | None = None, **kwargs: object) -> str:
    if not message_allowed(*keys, explicit_cap=cap):
        return default
    node: object = _active_domain()
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
