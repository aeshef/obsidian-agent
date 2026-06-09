"""Deploy branch logic for onboarding finalize phase (OSS — no host-specific defaults)."""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

from shared.capabilities.onboarding_interview import (
    InterviewQuestion,
    question_by_id,
    questions_for_profile,
)
from shared.capabilities.profile import CapabilityProfile, get_capabilities
from shared.yaml_config import load_yaml

DEPLOY_MODE_LOCAL = "local"
DEPLOY_MODE_VPS_NOW = "vps_now"
DEPLOY_MODE_VPS_LATER = "vps_later"

_REPO = Path(__file__).resolve().parents[2]
_HINTS_PATH = _REPO / "config" / "onboarding_deploy.yaml.example"

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


@lru_cache(maxsize=1)
def _hints_doc() -> dict:
    doc = load_yaml(_HINTS_PATH, default={}) or {}
    return doc if isinstance(doc, dict) else {}


def _hint_block(key: str, locale: str) -> list[str]:
    loc = "ru" if (locale or "").strip().lower().startswith("ru") else "en"
    hints = _hints_doc().get("hints", {})
    block = hints.get(key, {}) if isinstance(hints, dict) else {}
    if not isinstance(block, dict):
        return []
    lines = block.get(loc)
    return [str(x) for x in lines] if isinstance(lines, list) else []


def _choice_matches_label(choice: str, label: str) -> bool:
    c = choice.strip()
    lab = label.strip()
    if not c or not lab:
        return False
    if c == lab or c in lab or lab in c:
        return True
    return False


def normalize_deploy_mode(choice: str) -> str:
    q = question_by_id("deploy_target")
    c = (choice or "").strip()
    if q and q.deploy_modes:
        for i, mode in enumerate(q.deploy_modes):
            labels: list[str] = []
            if i < len(q.choices_en):
                labels.append(q.choices_en[i])
            if i < len(q.choices_ru):
                labels.append(q.choices_ru[i])
            if any(_choice_matches_label(c, lab) for lab in labels):
                return mode
    low = c.lower()
    if "local" in low or "computer only" in low or "mac" in low or "pc" in low:
        return DEPLOY_MODE_LOCAL
    if "later" in low or "checklist" in low:
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
    from shared.capabilities.onboarding_interview import _module_active

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


def _is_negative_choice(qid: str, answer: str) -> bool:
    q = question_by_id(qid)
    if not q or q.negative_choice_index is None:
        return False
    idx = q.negative_choice_index
    a = (answer or "").strip()
    labels = []
    if idx < len(q.choices_en):
        labels.append(q.choices_en[idx])
    if idx < len(q.choices_ru):
        labels.append(q.choices_ru[idx])
    return a in labels


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
            ans = str((state.get("answers") or {}).get("deploy_vps_ack", ""))
            if _is_negative_choice("deploy_vps_ack", ans) and not state.get("deploy_deferred"):
                errors.append("VPS deploy not finished — complete deploy.sh or choose later")
    return errors


def deploy_hint_lines(state: dict, locale: str = "en") -> list[str]:
    """Agent-facing checklist (no secrets)."""
    mode = deploy_mode(state) or ""
    if mode == DEPLOY_MODE_LOCAL:
        return _hint_block("local", locale)
    lines = list(_hint_block("vps_base", locale))
    if mode == DEPLOY_MODE_VPS_LATER:
        lines.extend(_hint_block("vps_later_tail", locale))
        return lines
    lines.extend(_hint_block("vps_now_tail", locale))
    return lines
