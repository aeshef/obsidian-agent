"""Capability gates for planning reply menus (config/ui_capabilities.yaml)."""
from __future__ import annotations

from shared.capabilities.ui_bindings import message_allowed


def planning_auto_allowed(auto_key: str) -> bool:
    return message_allowed("planning", auto_key)


def planning_submenu_allowed(kind: str) -> bool:
    return message_allowed("planning", "submenu", kind)
