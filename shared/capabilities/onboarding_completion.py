"""Onboarding completion gates — one checklist for /setup and smoke."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Optional

from shared.agent.config import agent_config_dir
from shared.capabilities.onboarding_deploy import (
    deploy_completion_errors,
    interview_incomplete_ids,
)
from shared.capabilities.profile import MODULE_FINANCE, CapabilityProfile, get_capabilities
from shared.capabilities.prompt_dirs import prompt_path_enabled
from shared.capabilities.prompt_manifest import personalized_prompts
from shared.prompts import _is_comment_stub
from shared.yaml_config import load_yaml

_REPO = Path(__file__).resolve().parents[2]


def _env_nonempty(key: str) -> bool:
    return bool((os.environ.get(key) or "").strip())


def _load_state() -> dict:
    path = agent_config_dir() / "onboarding_state.yaml"
    if not path.is_file():
        return {}
    data = load_yaml(path, default={}) or {}
    return data if isinstance(data, dict) else {}


def _slots_path() -> Path:
    return agent_config_dir() / "onboarding_slots.yaml"


def _slots_look_filled() -> bool:
    path = _slots_path()
    if not path.is_file():
        return False
    text = path.read_text(encoding="utf-8")
    placeholders = (
        "YOUR_TELEGRAM",
        "(fill during onboarding",
        "Wallet, Main card",
        "Food, Transport",
    )
    return not any(p in text for p in placeholders)


def _initial_accounts_ready(prof: CapabilityProfile) -> tuple[bool, str]:
    if not prof.module(MODULE_FINANCE):
        return True, "n/a"
    path = _REPO / "finance_bot" / "config" / "initial_accounts.yaml"
    if not path.is_file():
        return False, "finance_bot/config/initial_accounts.yaml missing"
    data = load_yaml(path, default={}) or {}
    tid = str(data.get("telegram_id") or "").strip()
    if not tid or tid.startswith("YOUR_") or not tid.isdigit():
        return False, "initial_accounts.yaml: set numeric telegram_id"
    accounts = data.get("accounts")
    if not isinstance(accounts, list) or not accounts:
        return False, "initial_accounts.yaml: accounts list empty"
    return True, "ok"


def _prompt_stubs_for_enabled(prof: CapabilityProfile) -> list[str]:
    missing: list[str] = []
    for rel_ex in personalized_prompts():
        if not prompt_path_enabled(rel_ex, prof):
            continue
        prod = _REPO / rel_ex.replace(".example.txt", ".txt")
        if not prod.is_file():
            missing.append(str(prod.relative_to(_REPO)))
            continue
        if _is_comment_stub(prod.read_text(encoding="utf-8").strip()):
            missing.append(str(prod.relative_to(_REPO)))
    return sorted(missing)


def _interview_incomplete(prof: CapabilityProfile, locale: str) -> list[str]:
    state = _load_state()
    return interview_incomplete_ids(prof, state, locale)


def completion_report(
    profile: Optional[CapabilityProfile] = None,
    *,
    locale: str = "en",
    strict_interview: bool = False,
    validate_secrets: bool = False,
    ping_deepseek: bool = False,
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings)."""
    prof = profile or get_capabilities()
    errors: list[str] = []
    warnings: list[str] = []

    cap = agent_config_dir() / "capabilities.yaml"
    if not cap.is_file():
        errors.append("capabilities.yaml missing (run apply_capabilities_profile --write)")

    from shared.setup.env_secrets import validate_core_secrets

    se, sw = validate_core_secrets(
        ping_deepseek_api=ping_deepseek or validate_secrets,
        require_openrouter=prof.module("knowledge") and validate_secrets,
    )
    errors.extend(se)
    warnings.extend(sw)

    if not _slots_look_filled():
        warnings.append("onboarding_slots.yaml missing or still has placeholder values")

    ia_ok, ia_msg = _initial_accounts_ready(prof)
    if prof.module(MODULE_FINANCE) and not ia_ok:
        errors.append(ia_msg)

    stubs = _prompt_stubs_for_enabled(prof)
    if stubs:
        errors.append(f"prod prompts still stubs ({len(stubs)}): " + ", ".join(stubs[:5]))

    profile_path = agent_config_dir() / "user_profile.md"
    if not profile_path.is_file() or len(profile_path.read_text(encoding="utf-8").strip()) < 40:
        warnings.append("user_profile.md empty or very short")

    incomplete = _interview_incomplete(prof, locale)
    if incomplete:
        msg = f"interview incomplete: {', '.join(incomplete)}"
        if strict_interview:
            errors.append(msg)
        else:
            warnings.append(msg)

    state = _load_state()
    if strict_interview and not state.get("bot_smoke_confirmed"):
        errors.append(
            "bot live smoke not confirmed — user must /start, send a test expense, then confirm-bot"
        )
    if strict_interview:
        errors.extend(deploy_completion_errors(state, strict=True))

    return errors, warnings


def is_complete(**kwargs) -> bool:
    errors, _ = completion_report(**kwargs)
    return not errors
