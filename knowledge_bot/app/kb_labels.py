"""English docstring; user strings live in YAML configs."""
from __future__ import annotations

from shared.i18n import msg


def kb_button(key: str) -> str:
    return msg("knowledge", "buttons", key)


def bulk_on() -> str:
    return kb_button("bulk_on")


def bulk_off() -> str:
    return kb_button("bulk_off")


def query_button() -> str:
    return kb_button("query")


def query_legacy() -> str:
    return kb_button("query_legacy")


def preview_save() -> str:
    return kb_button("preview_save")


def preview_type() -> str:
    return kb_button("preview_type")


def preview_cancel() -> str:
    return kb_button("preview_cancel")
