#!/usr/bin/env python3
"""Promote completed staging goals mapping to production (server or local)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from planning_bot.core.config import MAPPING_FILE, VAULT_PATH
from shared.goals.mapping_files import (
    clear_remap_in_progress,
    promote_mapping_file,
    staging_mapping_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", type=Path, default=VAULT_PATH)
    parser.add_argument("--staging", type=Path, default=None)
    parser.add_argument("--production", type=Path, default=None)
    args = parser.parse_args()

    vault = args.vault.expanduser().resolve()
    staging = (args.staging or staging_mapping_file(vault)).expanduser().resolve()
    production = (args.production or MAPPING_FILE).expanduser().resolve()
    if os.environ.get("GOALS_MAPPING_FILE"):
        production = Path(os.environ["GOALS_MAPPING_FILE"]).expanduser().resolve()

    promote_mapping_file(staging, production)
    clear_remap_in_progress(vault)
    print(f"promoted {staging} -> {production}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
