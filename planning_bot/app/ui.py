"""Short helpers for UI strings (config/messages.{locale}.yaml)."""
from __future__ import annotations

from shared.i18n import msg, msgf


def pmsg(key: str, default: str = "", **kwargs: object) -> str:
    """Strings under planning.messages.* in config/messages.{locale}.yaml."""
    if kwargs:
        out = msgf("planning", "messages", key, default=default, **kwargs)
        return out or msgf("planning", key, default=default, **kwargs)
    out = msg("planning", "messages", key, default=default)
    return out or msg("planning", key, default=default)


def pmsg_menu(key: str, default: str = "", **kwargs: object) -> str:
    if kwargs:
        return msgf("planning", "menu", key, default=default, **kwargs)
    return msg("planning", "menu", key, default=default)
