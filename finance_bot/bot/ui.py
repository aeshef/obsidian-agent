"""Short helpers for UI strings (config/messages.ru.yaml)."""
from __future__ import annotations

from shared.i18n import msg, msgf


def common(key: str, default: str = "", **kwargs: object) -> str:
    if kwargs:
        return msgf("common", key, default=default, **kwargs)
    return msg("common", key, default=default)
