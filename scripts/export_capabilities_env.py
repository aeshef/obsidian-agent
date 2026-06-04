#!/usr/bin/env python3
"""Print shell exports for obsidian_sync.sh (CAP_SYNC_*=0|1)."""
from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.capabilities.sync_steps import export_shell_env


def main() -> int:
    print(export_shell_env(), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
