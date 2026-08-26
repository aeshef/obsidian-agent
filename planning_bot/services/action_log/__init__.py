"""Action log package (split from action_logger monolith — OSS audit F13)."""
from __future__ import annotations

import logging
from pathlib import Path

from planning_bot.core.config import ACTION_LOGS_DIR
from planning_bot.core.pdmsg import pdmsg

from .aggregates import ActionLogAggregates
from .chains import ActionLogChains
from .io import ActionLogIO, _legacy_log_entry_re, _log_entry_re, _read_log_file
from .query import ActionLogQuery
from .write import ActionLogWrite

_log = logging.getLogger(__name__)

__all__ = [
    "ActionLogger",
    "_log_entry_re",
    "_legacy_log_entry_re",
    "_read_log_file",
]


class ActionLogger(
    ActionLogWrite,
    ActionLogQuery,
    ActionLogChains,
    ActionLogAggregates,
    ActionLogIO,
):
    def __init__(self, logs_dir: Path = ACTION_LOGS_DIR):
        self.logs_dir = Path(logs_dir).resolve()
        self.logs_dir.mkdir(parents=True, exist_ok=True)
        _log.debug(pdmsg("auto_913449b759"), self.logs_dir)
