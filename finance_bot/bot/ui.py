"""Short helpers for UI strings (config/messages.{locale}.yaml)."""
from __future__ import annotations

from shared.i18n import msg, msgf


def fmsg(key: str, default: str = "", **kwargs: object) -> str:
    if kwargs:
        return msgf("finance", key, default=default, **kwargs)
    return msg("finance", key, default=default)


def fin_menu(key: str, default: str = "", **kwargs: object) -> str:
    if kwargs:
        return msgf("finance", "menu", key, default=default, **kwargs)
    return msg("finance", "menu", key, default=default)
