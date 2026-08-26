"""CLI helpers for finance dashboard build."""
from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
from typing import Optional

from bot.vault_paths import VaultPaths


def find_vault_and_db(args) -> tuple[Path, Path, Path]:
    """Return (vault, db_path, out_path)."""
    if args.vault:
        vault = Path(args.vault).resolve()
    else:
        vault = VaultPaths().root
    vp = VaultPaths(vault)
    return vault, args.db or vp.finance_db(), args.out or vp.finance_dashboard_md()


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Finance dashboard from finance.db")
    parser.add_argument("--vault", type=Path, default=None, help="Vault root")
    parser.add_argument("--db", type=Path, default=None, help="Path to finance.db")
    parser.add_argument("--out", type=Path, default=None, help="Output markdown file")
    parser.add_argument("--user-id", type=int, default=1)
    return parser



def log_dashboard(msg: str, log_path: Optional[Path] = None) -> None:
    """Print and optionally append to log file (launchd/cron)."""
    print(msg)
    if log_path:
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"[{datetime.now().isoformat()}] {msg}\n")
        except Exception:
            pass


if __name__ == "__main__":
    import sys

    log_file = Path(__file__).resolve().parents[2] / "logs" / "build_finance_dashboard.log"
    log_file.parent.mkdir(parents=True, exist_ok=True)
    try:
        run_build(build_arg_parser().parse_args())
    except Exception as e:
        log_dashboard(f"ERROR: {e}", log_file)
        import traceback

        traceback.print_exc()
        sys.exit(1)
