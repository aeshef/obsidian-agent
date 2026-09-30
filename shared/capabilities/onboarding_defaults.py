"""Sensible intro-phase defaults for stranger fast path (<30 min)."""
from __future__ import annotations

from typing import Any

from shared.capabilities.profile import (
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    CapabilityProfile,
)

from shared.agent.config import agent_config_dir
from shared.yaml_config import load_merged_config


def intro_default_for(qid: str, locale: str, prof: CapabilityProfile) -> dict[str, Any] | None:
    """Return kwargs for onboarding_interview._apply_answer, or None if no default."""
    spec = load_merged_config(str(agent_config_dir()), "intro_defaults").get(qid)
    if spec is None:
        return None
    if qid == "finance_currency" and not prof.module(MODULE_FINANCE):
        return None
    if qid in ("finance_accounts", "finance_categories") and not prof.module(MODULE_FINANCE):
        return None
    if qid in ("planning_task_examples", "planning_goals") and not prof.module(MODULE_PLANNING):
        return None
    if qid == "knowledge_folders" and not prof.module(MODULE_KNOWLEDGE):
        return None

    loc = "ru" if (locale or "").strip().lower().startswith("ru") else "en"
    if "choice" in spec:
        return {"choice_index": int(spec["choice"])}
    if "choice_by_locale" in spec:
        by_loc = spec["choice_by_locale"]
        idx = int(by_loc.get(loc, by_loc.get("default", 0)))
        return {"choice_index": idx}
    if spec.get("mvp"):
        return {"use_mvp": True, "text": ""}
    text = spec.get(loc) or spec.get("en") or ""
    return {"text": str(text)}
