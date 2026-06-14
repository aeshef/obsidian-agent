#!/usr/bin/env python3
"""Vault audit report → vault dashboards (tracked entry point for obsidian_sync)."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from knowledge_bot.core.config import load_config
from knowledge_bot.services.vault_audit import write_vault_audit_report


def main() -> int:
    ap = argparse.ArgumentParser(description="Vault audit report (read-only)")
    ap.add_argument("--vault", default="", help="Vault root (default: VAULT_PATH)")
    ap.add_argument("--out", "-o", default="", help="Output .md (relative to vault or absolute)")
    args = ap.parse_args()

    vault = Path(args.vault).expanduser().resolve() if args.vault else load_config().vault_path
    out = Path(args.out).expanduser() if args.out else None
    path = write_vault_audit_report(vault, out)
    print(f"Report written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
