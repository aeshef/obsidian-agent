"""Load English scaffolds for personalized prod prompts (OSS first run).

Bodies live in checked-in ``*.example.txt`` files — not in this module.
Default ``{{PLACEHOLDER}}`` values: ``config/agent/prompt_scaffold_slots.yaml.example``.
"""
from __future__ import annotations

from pathlib import Path

from shared.yaml_config import load_yaml

_ROOT = Path(__file__).resolve().parents[2]
_SLOTS_EXAMPLE = _ROOT / "config" / "agent" / "prompt_scaffold_slots.yaml.example"

# Manifest paths that must have a matching *.example.txt on disk (no in-code bodies).
SCAFFOLDS: dict[str, str] = {}


def load_scaffold_body(repo_root: Path, rel_example: str) -> str | None:
    path = repo_root / rel_example
    if path.is_file():
        return path.read_text(encoding="utf-8")
    return SCAFFOLDS.get(rel_example)


def _load_default_slots() -> dict[str, str]:
    doc = load_yaml(_SLOTS_EXAMPLE, default={}) or {}
    out: dict[str, str] = {}
    if isinstance(doc, dict):
        for k, v in doc.items():
            if isinstance(k, str) and v is not None:
                out[k] = str(v).strip()
    return out


DEFAULT_SLOTS: dict[str, str] = _load_default_slots()
