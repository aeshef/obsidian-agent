#!/usr/bin/env python3
"""Print sync CAP_SYNC_* plan for obsidian_sync.sh (eval)."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.sync import export_sync_plan_shell  # noqa: E402


def main() -> int:
    print(export_sync_plan_shell(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
