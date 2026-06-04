#!/usr/bin/env python3
"""Create vault directories for the active capabilities profile (idempotent)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from shared.capabilities.profile import clear_capabilities_cache, load_capabilities
from shared.capabilities.vault_init import ensure_vault_layout, planned_vault_dirs
from shared.paths import vault_root_optional


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--vault", default="", help="Override VAULT_PATH")
    parser.add_argument("--dry-run", action="store_true", help="List dirs only, do not mkdir")
    args = parser.parse_args()

    if args.vault:
        os.environ["VAULT_PATH"] = args.vault
    root = vault_root_optional()
    if root is None:
        print("Set VAULT_PATH in .env or pass --vault", file=sys.stderr)
        return 1

    clear_capabilities_cache()
    prof = load_capabilities()
    planned = planned_vault_dirs(prof, root)
    if args.dry_run:
        for p in planned:
            print(p)
        return 0

    created = ensure_vault_layout(prof, root)
    if created:
        print(f"Created {len(created)} directories under {root}")
        for c in created:
            print(f"  + {c}")
    else:
        print(f"Vault layout OK ({len(planned)} dirs checked) under {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
