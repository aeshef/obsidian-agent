"""Compatibility shim — host composition root lives in ``unified_bot.host``.

Import from ``unified_bot.host`` in new code. This package re-exports for one release.
"""
from __future__ import annotations

from unified_bot.host.bootstrap import run_host_bot

__all__ = ["run_host_bot"]
