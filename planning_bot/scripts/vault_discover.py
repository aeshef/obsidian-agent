"""Vault discovery helpers for planning chart scripts."""
from __future__ import annotations

from pathlib import Path

from planning_bot.core.pdmsg import pdmsg


def discover_vault(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / pdmsg("auto_0785c86cb9")).exists() and (p / pdmsg("auto_1c7277d3a5")).exists():
            return p
    return start.parents[3]


def vault_layout(vault: Path) -> tuple[Path, Path, Path]:
    dash = vault / pdmsg("auto_1c7277d3a5")
    logs = dash / pdmsg("auto_bcc4709278")
    graphics = dash / pdmsg("auto_1f4101e6f4")
    return dash, logs, graphics
