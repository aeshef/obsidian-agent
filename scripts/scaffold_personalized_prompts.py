#!/usr/bin/env python3
"""Materialize prod *.txt from English scaffolds when still comment-only stubs."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

from shared.capabilities.profile import get_capabilities
from shared.capabilities.prompt_dirs import prompt_path_enabled
from shared.capabilities.prompt_manifest import personalized_prompts
from shared.capabilities.prompt_scaffold_templates import DEFAULT_SLOTS, SCAFFOLDS
from shared.prompts import _is_comment_stub
from shared.yaml_config import load_yaml

ROOT = Path(__file__).resolve().parents[1]
_SLOT_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def _load_slots(path: Path | None) -> dict[str, str]:
    slots = dict(DEFAULT_SLOTS)
    if path and path.is_file():
        doc = load_yaml(path, default={}) or {}
        if isinstance(doc, dict):
            for k, v in doc.items():
                if isinstance(k, str) and v is not None:
                    slots[k] = str(v).strip()
    return slots


def _apply_slots(text: str, slots: dict[str, str]) -> str:
    def repl(m: re.Match[str]) -> str:
        key = m.group(1)
        return slots.get(key, m.group(0))

    return _SLOT_RE.sub(repl, text)


def scaffold_one(rel_example: str, slots: dict[str, str], dry_run: bool) -> str | None:
    body = SCAFFOLDS.get(rel_example)
    if not body:
        return f"no scaffold for {rel_example}"
    prod = ROOT / rel_example.replace(".example.txt", ".txt")
    if prod.is_file() and not _is_comment_stub(prod.read_text(encoding="utf-8")):
        return None
    text = _apply_slots(body.strip() + "\n", slots)
    if dry_run:
        return f"would write {prod.relative_to(ROOT)}"
    prod.parent.mkdir(parents=True, exist_ok=True)
    prod.write_text(text, encoding="utf-8")
    return f"scaffolded {prod.relative_to(ROOT)}"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--slots",
        type=Path,
        default=ROOT / "config/agent/onboarding_slots.yaml",
        help="YAML with {{PLACEHOLDER}} values (optional)",
    )
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    slots_path = args.slots if args.slots.is_file() else None
    slots = _load_slots(slots_path)
    prof = get_capabilities()
    actions: list[str] = []
    missing_scaffold: list[str] = []

    for rel in sorted(personalized_prompts()):
        if not prompt_path_enabled(rel, prof):
            continue
        if rel not in SCAFFOLDS:
            missing_scaffold.append(rel)
            continue
        msg = scaffold_one(rel, slots, args.dry_run)
        if msg:
            actions.append(msg)

    for line in actions:
        print(line)
    if missing_scaffold:
        print("missing SCAFFOLDS entries:", ", ".join(missing_scaffold), sep="\n")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
