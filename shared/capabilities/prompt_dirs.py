"""Prompt directories to materialize for the active capability profile."""
from __future__ import annotations

from shared.capabilities.profile import (
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    CapabilityProfile,
    get_capabilities,
)

_AGENT_PROMPTS = "config/agent/prompts"
_FINANCE_PROMPTS = "finance_bot/config/prompts"
_KNOWLEDGE_PROMPTS = "knowledge_bot/config/prompts"
_PLANNING_PROMPTS = "planning_bot/config/prompts"


def prompt_dirs_for_profile(profile: CapabilityProfile | None = None) -> tuple[str, ...]:
    """Repo-relative prompt dirs for enabled modules (agent prompts always)."""
    prof = profile or get_capabilities()
    dirs: list[str] = [_AGENT_PROMPTS]
    if prof.module(MODULE_FINANCE):
        dirs.append(_FINANCE_PROMPTS)
    if prof.module(MODULE_KNOWLEDGE):
        dirs.append(_KNOWLEDGE_PROMPTS)
    if prof.module(MODULE_PLANNING):
        dirs.append(_PLANNING_PROMPTS)
    return tuple(dirs)


def prompt_path_enabled(rel_path: str, profile: CapabilityProfile | None = None) -> bool:
    """Whether a repo-relative prompts/*.example.txt path belongs to an enabled module."""
    norm = rel_path.replace("\\", "/").strip()
    if norm.startswith(f"{_AGENT_PROMPTS}/"):
        return True
    prof = profile or get_capabilities()
    if norm.startswith(f"{_FINANCE_PROMPTS}/"):
        return prof.module(MODULE_FINANCE)
    if norm.startswith(f"{_KNOWLEDGE_PROMPTS}/"):
        return prof.module(MODULE_KNOWLEDGE)
    if norm.startswith(f"{_PLANNING_PROMPTS}/"):
        return prof.module(MODULE_PLANNING)
    return True
