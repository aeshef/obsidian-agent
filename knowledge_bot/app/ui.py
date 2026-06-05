"""Knowledge UI strings (config/messages.ru.yaml)."""
from __future__ import annotations

from shared.i18n import msg, msgf


def kmsg(*keys: str, default: str = "", **kwargs: object) -> str:
    if kwargs:
        return msgf("knowledge", *keys, default=default, **kwargs)
    return msg("knowledge", *keys, default=default)
