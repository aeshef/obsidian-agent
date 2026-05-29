"""Layer 0: persistent user profile from markdown."""
from __future__ import annotations

import logging
from pathlib import Path

from shared.agent.types import AgentContext, AgentMessage

log = logging.getLogger("shared.memory.profile")


class ProfileMemory:
    def __init__(self, path: Path, *, header: str | None = None) -> None:
        self._path = path
        self._header = header

    async def read(self, ctx: AgentContext) -> str:
        if not self._path.exists():
            return ""
        try:
            text = self._path.read_text(encoding="utf-8").strip()
        except OSError as e:
            log.warning("profile read failed %s: %s", self._path, e)
            return ""
        if not text:
            return ""
        return f"{self._header}\n{text}"

    async def write(self, ctx: AgentContext, turn: AgentMessage) -> None:
        pass
