#!/usr/bin/env python3
"""Idempotently append obsidian-agent shell helpers to ~/.zshrc or ~/.bashrc."""
from __future__ import annotations

import argparse
import os
from pathlib import Path

_MARKER_BEGIN = "# obsidian-agent-onboarding-begin"
_MARKER_END = "# obsidian-agent-onboarding-end"


def _block(agent_root: Path) -> str:
    root = str(agent_root.resolve())
    return f"""{_MARKER_BEGIN}
# Managed by scripts/setup/update_shellrc.py — safe to re-run
export PYTHONIOENCODING=utf-8
export AGENT_ROOT="{root}"
oa-load-env() {{
  # load-env
  set -a
  # shellcheck disable=SC1091
  source "$AGENT_ROOT/scripts/setup/load_env.sh"
  set +a
}}
{_MARKER_END}
"""


def _strip_managed(text: str) -> str:
    begin = text.find(_MARKER_BEGIN)
    if begin < 0:
        return text.rstrip() + "\n"
    end = text.find(_MARKER_END, begin)
    if end < 0:
        return text[:begin].rstrip() + "\n"
    end = text.find("\n", end)
    if end < 0:
        end = len(text)
    else:
        end += 1
    head = text[:begin].rstrip()
    tail = text[end:].lstrip("\n")
    if head and tail:
        return head + "\n\n" + tail
    if head:
        return head + "\n"
    return tail + ("\n" if tail and not tail.endswith("\n") else "")


def patch_rc(rc_path: Path, agent_root: Path, *, dry_run: bool) -> str:
    block = _block(agent_root)
    if rc_path.is_file():
        body = _strip_managed(rc_path.read_text(encoding="utf-8"))
        new_body = body.rstrip() + "\n\n" + block if body.strip() else block + "\n"
    else:
        new_body = block + "\n"
    if dry_run:
        return "dry-run"
    rc_path.parent.mkdir(parents=True, exist_ok=True)
    rc_path.write_text(new_body, encoding="utf-8")
    return "updated"


def default_rc() -> Path:
    shell = (os.environ.get("SHELL") or "").lower()
    home = Path.home()
    if "zsh" in shell:
        return home / ".zshrc"
    if "bash" in shell:
        return home / ".bashrc"
    return home / ".zshrc"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rc-file", default="", help="Target rc file (default: ~/.zshrc or ~/.bashrc)")
    parser.add_argument("--agent-root", default="", help="Repo root (default: parent of scripts/)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.agent_root) if args.agent_root else Path(__file__).resolve().parents[2]
    rc = Path(args.rc_file) if args.rc_file else default_rc()
    status = patch_rc(rc, root, dry_run=args.dry_run)
    print(f"update_shellrc: {status} {rc}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
