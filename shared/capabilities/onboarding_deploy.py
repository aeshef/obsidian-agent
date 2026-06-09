"""Deploy branch logic for onboarding finalize phase (OSS — no host-specific defaults)."""
from __future__ import annotations

import os
import re
from typing import Optional

from shared.capabilities.onboarding_interview import (
    InterviewQuestion,
    questions_for_profile,
)
from shared.capabilities.profile import CapabilityProfile, get_capabilities

DEPLOY_MODE_LOCAL = "local"
DEPLOY_MODE_VPS_NOW = "vps_now"
DEPLOY_MODE_VPS_LATER = "vps_later"

_PLACEHOLDER_SERVERS = frozenset(
    {
        "",
        "your-ssh-host",
        "your_ssh_host",
        "example.com",
        "hostname",
        "changeme",
    }
)


def normalize_deploy_mode(choice: str) -> str:
    c = (choice or "").strip().lower()
    if any(k in c for k in ("mac", "локаль", "local", "computer only", "этот комп", "этот mac")):
        return DEPLOY_MODE_LOCAL
    if any(k in c for k in ("позже", "later", "потом", "чеклист", "checklist")):
        return DEPLOY_MODE_VPS_LATER
    return DEPLOY_MODE_VPS_NOW


def deploy_mode(state: dict) -> Optional[str]:
    mode = state.get("deploy_mode")
    if isinstance(mode, str) and mode:
        return mode
    ans = (state.get("answers") or {}).get("deploy_target", "")
    if ans:
        return normalize_deploy_mode(str(ans))
    return None


def is_question_visible(qid: str, state: dict, prof: Optional[CapabilityProfile] = None) -> bool:
    from shared.capabilities.onboarding_interview import _module_active, question_by_id

    q = question_by_id(qid)
    if q is None:
        return False
    prof = prof or get_capabilities()
    if not _module_active(q, prof):
        return False

    mode = deploy_mode(state)
    if qid == "deploy_target":
        return True
    if mode is None:
        return False

    if qid == "deploy_local_ack":
        return mode == DEPLOY_MODE_LOCAL
    if qid == "deploy_ssh_host":
        return mode in (DEPLOY_MODE_VPS_NOW, DEPLOY_MODE_VPS_LATER)
    if qid == "deploy_ssh_key_ready":
        return mode in (DEPLOY_MODE_VPS_NOW, DEPLOY_MODE_VPS_LATER)
    if qid == "deploy_vps_ack":
        return mode == DEPLOY_MODE_VPS_NOW
    if qid == "deploy_vps_later_ack":
        return mode == DEPLOY_MODE_VPS_LATER
    return True


def iter_visible_questions(
    prof: Optional[CapabilityProfile] = None,
    *,
    phase: Optional[str] = None,
    locale: str = "en",
    state: Optional[dict] = None,
) -> list[InterviewQuestion]:
    prof = prof or get_capabilities()
    st = state or {}
    out: list[InterviewQuestion] = []
    for q in questions_for_profile(prof, phase=phase, locale=locale):
        if is_question_visible(q.id, st, prof):
            out.append(q)
    return out


def interview_incomplete_ids(
    prof: CapabilityProfile,
    state: dict,
    locale: str = "en",
) -> list[str]:
    done = set(state.get("completed") or [])
    missing: list[str] = []
    for phase in ("intro", "before_layout", "after_layout", "after_secrets", "finalize"):
        for q in iter_visible_questions(prof, phase=phase, locale=locale, state=state):
            if q.id not in done:
                missing.append(q.id)
    return missing


def server_env_ok() -> bool:
    raw = (os.environ.get("SERVER") or "").strip().strip('"').strip("'")
    low = raw.lower()
    if low in _PLACEHOLDER_SERVERS:
        return False
    if "your" in low and "host" in low:
        return False
    return bool(raw)


def ssh_host_sanitized(raw: str) -> str:
    s = (raw or "").strip().strip('"').strip("'")
    s = re.sub(r"\s+", "", s)
    if "@" not in s and s and not s.startswith("ssh "):
        s = f"root@{s}"
    return s


def deploy_completion_errors(state: dict, *, strict: bool) -> list[str]:
    if not strict:
        return []
    errors: list[str] = []
    mode = deploy_mode(state)
    if not mode:
        errors.append("deploy_target not answered (finalize phase)")
        return errors

    if mode == DEPLOY_MODE_LOCAL:
        if "deploy_local_ack" not in set(state.get("completed") or []):
            errors.append("deploy_local_ack missing — confirm local-only limitations")
        return errors

    if "deploy_ssh_host" not in set(state.get("completed") or []):
        errors.append("deploy_ssh_host missing — set SERVER (SSH user@host)")
    elif not server_env_ok():
        errors.append("SERVER in .env missing or still placeholder")

    if mode == DEPLOY_MODE_VPS_LATER:
        if "deploy_vps_later_ack" not in set(state.get("completed") or []):
            errors.append("deploy_vps_later_ack missing — save deploy checklist")
        return errors

    if mode == DEPLOY_MODE_VPS_NOW:
        if "deploy_vps_ack" not in set(state.get("completed") or []):
            errors.append("deploy_vps_ack missing — run deploy or mark deferred")
        elif not state.get("deploy_success") and not state.get("deploy_deferred"):
            ans = (state.get("answers") or {}).get("deploy_vps_ack", "").lower()
            if "fail" in ans or "retry" in ans or "позже" in ans or "потом" in ans:
                if not state.get("deploy_deferred"):
                    errors.append("VPS deploy not finished — complete deploy.sh or choose later")
    return errors


def deploy_hint_lines(state: dict, locale: str = "en") -> list[str]:
    """Agent-facing checklist (no secrets)."""
    loc = (locale or "en").strip().lower()
    mode = deploy_mode(state) or ""
    ru = loc.startswith("ru")

    if mode == DEPLOY_MODE_LOCAL:
        return [
            "Локальный режим: бот работает только пока включён Mac."
            if ru
            else "Local mode: bot runs only while this computer is on.",
            "./scripts/run_unified_bot.sh",
            "Опционально 24/7: docs/DEPLOY_VPS.md + ./scripts/install_mac_sync.sh"
            if ru
            else "Optional 24/7: docs/DEPLOY_VPS.md + ./scripts/install_mac_sync.sh",
        ]

    lines = [
        "Минимум VPS: 1 vCPU, 1 GB RAM, 20 GB disk, Ubuntu 22.04+."
        if ru
        else "Minimum VPS: 1 vCPU, 1 GB RAM, 20 GB disk, Ubuntu 22.04+.",
        "docs/DEPLOY_VPS.md",
    ]
    if mode == DEPLOY_MODE_VPS_LATER:
        lines.append(
            "Сохрани чеклист; когда VPS будет — SERVER в .env и ./scripts/deploy.sh --prod"
            if ru
            else "Save checklist; when VPS is ready: SERVER in .env, then ./scripts/deploy.sh --prod"
        )
        return lines

    lines.extend(
        [
            "SSH: только ключи (пароль root в чат не присылайте)."
            if ru
            else "SSH: keys only (never paste root password in chat).",
            "ssh-copy-id user@your-server",
            "./scripts/deploy.sh --prod --install-deps",
            "На Mac: ./scripts/install_mac_sync.sh (vault ↔ VPS)",
        ]
    )
    return lines
