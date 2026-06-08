#!/usr/bin/env python3
"""Resolve scripts.* UI strings from config/messages.{locale}.yaml for shell echo."""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
for p in (ROOT / "finance_bot", ROOT):
    sp = str(p)
    if sp not in sys.path:
        sys.path.insert(0, sp)


def main() -> int:
    if len(sys.argv) < 3:
        return 2
    mode = sys.argv[1]
    keys = sys.argv[2].split(".")
    from shared.i18n import msg, msgf

    if mode == "msgf":
        if len(sys.argv) < 4:
            return 2
        kwargs = json.loads(sys.argv[3])
        print(msgf(*keys, **kwargs), end="")
        return 0
    if mode == "msg":
        default = sys.argv[3] if len(sys.argv) > 3 else ""
        print(msg(*keys, default=default), end="")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
