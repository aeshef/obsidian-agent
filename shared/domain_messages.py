"""Non-UI domain strings (tool output, lookup reasons) — config/domain_messages.{locale}.yaml."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from shared.capabilities.ui_bindings import message_allowed
from shared.locale import agent_locale
from shared.yaml_config import deep_merge, load_runtime_config

_REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


@lru_cache(maxsize=2)
def _domain_for_stem(stem: str) -> dict:
    return load_runtime_config(str(_REPO_CONFIG), stem)


@lru_cache(maxsize=2)
def _domain(_locale: str) -> dict:
    if _locale.startswith("en"):
        ru = _domain_for_stem("domain_messages.ru")
        en = _domain_for_stem("domain_messages.en")
        if ru and en:
            return deep_merge(ru, en)
        return en or ru
    return _domain_for_stem("domain_messages.ru")


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
