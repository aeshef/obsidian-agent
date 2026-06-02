"""Planning domain strings from config/domain_messages.yaml (not Telegram UI)."""
from __future__ import annotations

from shared.domain_messages import dmsg


def pdmsg(*keys: str, default: str = "", **kwargs: object) -> str:
    return dmsg("planning", *keys, default=default, **kwargs)


def pdmsg_nl(*keys: str, default: str = "", **kwargs: object) -> str:
    """Fragment for Telegram message assembly (YAML `|` blocks strip trailing \\n)."""
    s = pdmsg(*keys, default=default, **kwargs)
    return s if s.endswith("\n") else f"{s}\n"
