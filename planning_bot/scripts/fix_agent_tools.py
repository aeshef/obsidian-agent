#!/usr/bin/env python3
"""One-shot patcher for app/agent_tools.py (run only when migrating strings)."""
from __future__ import annotations

from pathlib import Path

TARGET = Path(__file__).resolve().parents[1] / "app" / "agent_tools.py"

IMPORTS = (
    "from planning_bot.core.config import DEFAULT_CATEGORY, DEFAULT_PRIORITY\n"
    "from planning_bot.core.pdmsg import pdmsg\n\n"
)


def main() -> None:
    src = TARGET.read_text(encoding="utf-8")
    if "from planning_bot.core.pdmsg import pdmsg" not in src:
        src = src.replace(
            "from __future__ import annotations\n\n",
            "from __future__ import annotations\n\n" + IMPORTS,
            1,
        )
        TARGET.write_text(src, encoding="utf-8")
    print("ok (agent_tools already uses pdmsg)")


if __name__ == "__main__":
    main()
