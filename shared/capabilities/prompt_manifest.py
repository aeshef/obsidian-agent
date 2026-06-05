"""Prompt file tiers for OSS onboarding (generic English vs skill-filled)."""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from shared.yaml_config import load_merged_config

PromptTier = Literal["generic_en", "personalized", "stub"]

_REPO_CONFIG = Path(__file__).resolve().parents[2] / "config"
_REPO_ROOT = _REPO_CONFIG.parent


@lru_cache(maxsize=1)
def _manifest() -> dict:
    return load_merged_config(str(_REPO_CONFIG), "prompt_manifest")


def _tier_paths(key: str) -> frozenset[str]:
    raw = _manifest().get(key)
    if not isinstance(raw, list):
        return frozenset()
    return frozenset(str(p).strip() for p in raw if str(p).strip())


def generic_en_prompts() -> frozenset[str]:
    return _tier_paths("generic_en")


def generic_en_prefixes() -> frozenset[str]:
    return _tier_paths("generic_en_prefixes")


def personalized_prompts() -> frozenset[str]:
    return _tier_paths("personalized")


def prompt_tier(rel_path: str) -> PromptTier:
    """Classify repo-relative path to prompts/*.example.txt."""
    norm = rel_path.replace("\\", "/").strip()
    if norm in generic_en_prompts():
        return "generic_en"
    for prefix in generic_en_prefixes():
        if norm.startswith(prefix):
            return "generic_en"
    if norm in personalized_prompts():
        return "personalized"
    return "personalized"


def list_tracked_example_prompts() -> list[str]:
    import subprocess

    out = subprocess.check_output(
        ["git", "ls-files", "**/*.example.txt"],
        cwd=_REPO_ROOT,
        text=True,
    ).strip()
    return [p for p in out.splitlines() if p]


def prompts_missing_prod_text() -> list[str]:
    """Prod .txt missing or still comment-only stub."""
    from shared.prompts import _is_comment_stub

    missing: list[str] = []
    for rel in list_tracked_example_prompts():
        prod = _REPO_ROOT / rel.replace(".example.txt", ".txt")
        if not prod.is_file():
            missing.append(rel.replace(".example.txt", ".txt"))
            continue
        if _is_comment_stub(prod.read_text(encoding="utf-8").strip()):
            missing.append(str(prod.relative_to(_REPO_ROOT)))
    return sorted(missing)


def clear_prompt_manifest_cache() -> None:
    _manifest.cache_clear()
