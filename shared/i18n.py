"""UI strings from config/messages.{locale}.yaml (examples in git: en + ru)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from shared.capabilities.ui_bindings import message_allowed
from shared.locale import is_english, messages_stem
from shared.yaml_config import load_runtime_config

_REPO_CONFIG = Path(__file__).resolve().parent.parent / "config"


@lru_cache(maxsize=2)
def messages() -> dict:
    stem = messages_stem()
    cfg = load_runtime_config(str(_REPO_CONFIG), stem)
    if cfg:
        return cfg
    # Missing local file: other locale example (first-run clone).
    fallback = "messages.ru" if is_english() else "messages.en"
    return load_runtime_config(str(_REPO_CONFIG), fallback)


def clear_messages_cache() -> None:
    messages.cache_clear()


def _msg_node(*keys: str) -> object | None:
    node: object = messages()
    for k in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(k)
    return node


def msg_raw(*keys: str, default: str = "") -> str:
    """Resolve message text ignoring ui_capabilities gates (NLU command filtering)."""
    node = _msg_node(*keys)
    if node is None:
        return default
    s = str(node)
    return s.strip(" \t\r") if "\n" not in s else s


def msg(*keys: str, default: str = "", cap: str | None = None) -> str:
    if not message_allowed(*keys, explicit_cap=cap):
        return default
    node = _msg_node(*keys)
    if node is None:
        return default
    s = str(node)
    return s.strip(" \t\r") if "\n" not in s else s


def msgf(*keys: str, default: str = "", cap: str | None = None, **kwargs: object) -> str:
    template = msg(*keys, default=default, cap=cap)
    if not template:
        return default
    try:
        return template.format(**kwargs)
    except (KeyError, ValueError):
        return template
