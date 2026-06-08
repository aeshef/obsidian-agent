#!/usr/bin/env python3
"""Validate onboarding secrets (placeholders + optional DeepSeek ping)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.capabilities.profile import MODULE_KNOWLEDGE, get_capabilities
from shared.setup.load_env import load_repo_env
from shared.setup.env_secrets import validate_core_secrets


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--ping-deepseek",
        action="store_true",
        help="Call DeepSeek API once to verify the key (small cost)",
    )
    args = ap.parse_args()
    load_repo_env(_ROOT)
    prof = get_capabilities()
    errors, warnings = validate_core_secrets(
        ping_deepseek_api=args.ping_deepseek,
        require_openrouter=prof.module(MODULE_KNOWLEDGE),
    )
    for w in warnings:
        print(f"warn: {w}")
    for e in errors:
        print(f"ERR: {e}")
    if errors:
        return 1
    print("secrets OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
