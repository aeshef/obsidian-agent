#!/usr/bin/env python3
"""Daily 700_ maintenance (hubs, wikilinks, optional reprocess) — config/vault_maintenance.yaml.

  python tools/vault_daily_maintenance.py
  python tools/vault_daily_maintenance.py --force
  python tools/vault_daily_maintenance.py --sync-dir "/path/to/.sync"

Called from obsidian_sync.sh step 5b.2 with SYNC_STATE_DIR.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

# Agent on PYTHONPATH
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from knowledge_bot.services.vault_maintenance import run_daily_maintenance


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="Ignore today's marker")
    ap.add_argument(
        "--sync-dir",
        type=Path,
        help="Marker directory (.sync); default $SYNC_STATE_DIR or vault/.sync",
    )
    ap.add_argument("--json", action="store_true", help="Print JSON (for logs)")
    args = ap.parse_args()
    print("[vault_daily_maintenance] start", flush=True)
    out = run_daily_maintenance(sync_dir=args.sync_dir, force=args.force)
    if args.json:
        print(json.dumps(out, ensure_ascii=False, default=str, indent=2))
    else:
        print("vault_daily_maintenance:", "ok" if out.get("ok", True) else "ERR", out)


if __name__ == "__main__":
    main()
