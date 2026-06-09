"""Structured onboarding interview — question catalog for Cursor /setup chat."""
from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Literal, Optional

from shared.capabilities.profile import (
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    CapabilityProfile,
    get_capabilities,
)
from shared.yaml_config import load_yaml

InterviewPhase = Literal[
    "intro",
    "before_layout",
    "after_layout",
    "after_secrets",
    "finalize",
]
AnswerKind = Literal["text", "comma_list", "accounts", "account_balances", "choice"]

_REPO = Path(__file__).resolve().parents[2]
_CATALOG_PATH = _REPO / "config" / "onboarding_interview.yaml.example"

_MODULE_ALIASES = {
    "finance": MODULE_FINANCE,
    "planning": MODULE_PLANNING,
    "knowledge": MODULE_KNOWLEDGE,
}


@dataclass(frozen=True)
class InterviewQuestion:
    id: str
    phase: InterviewPhase
    modules: tuple[str, ...]  # empty = always (core)
    kind: AnswerKind
    prompt_en: str
    prompt_ru: str
    slot_keys: tuple[str, ...] = ()
    choices_en: tuple[str, ...] = ()
    choices_ru: tuple[str, ...] = ()
    deploy_modes: tuple[str, ...] = ()
    negative_choice_index: Optional[int] = None


CORE: tuple[str, ...] = ()


def _parse_modules(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return CORE
    out: list[str] = []
    for item in raw:
        key = str(item).strip()
        mod = _MODULE_ALIASES.get(key, key)
        if mod:
            out.append(mod)
    return tuple(out)


@lru_cache(maxsize=1)
def _load_catalog() -> tuple[InterviewQuestion, ...]:
    doc = load_yaml(_CATALOG_PATH, default={}) or {}
    raw_q = doc.get("questions")
    if not isinstance(raw_q, dict):
        return ()
    out: list[InterviewQuestion] = []
    for qid, spec in raw_q.items():
        if not isinstance(spec, dict):
            continue
        choices_en = tuple(str(x) for x in (spec.get("choices_en") or ()))
        choices_ru = tuple(str(x) for x in (spec.get("choices_ru") or ()))
        slot_keys = tuple(str(x) for x in (spec.get("slot_keys") or ()))
        deploy_modes = tuple(str(x) for x in (spec.get("deploy_modes") or ()))
        neg = spec.get("negative_choice_index")
        out.append(
            InterviewQuestion(
                id=str(qid),
                phase=str(spec.get("phase") or "intro"),  # type: ignore[arg-type]
                modules=_parse_modules(spec.get("modules")),
                kind=str(spec.get("kind") or "text"),  # type: ignore[arg-type]
                prompt_en=str(spec.get("prompt_en") or ""),
                prompt_ru=str(spec.get("prompt_ru") or ""),
                slot_keys=slot_keys,
                choices_en=choices_en,
                choices_ru=choices_ru,
                deploy_modes=deploy_modes,
                negative_choice_index=int(neg) if neg is not None else None,
            )
        )
    return tuple(out)


def QUESTIONS() -> tuple[InterviewQuestion, ...]:
    return _load_catalog()


def _module_active(q: InterviewQuestion, prof: CapabilityProfile) -> bool:
    if not q.modules:
        return True
    return any(prof.module(m) for m in q.modules)


def questions_for_profile(
    profile: Optional[CapabilityProfile] = None,
    *,
    phase: Optional[InterviewPhase] = None,
    locale: str = "en",
) -> list[InterviewQuestion]:
    prof = profile or get_capabilities()
    out: list[InterviewQuestion] = []
    for q in QUESTIONS():
        if not _module_active(q, prof):
            continue
        if phase is not None and q.phase != phase:
            continue
        out.append(q)
    return out


def prompt_for(q: InterviewQuestion, locale: str) -> str:
    loc = (locale or "en").strip().lower()
    return q.prompt_ru if loc.startswith("ru") else q.prompt_en


def choices_for(q: InterviewQuestion, locale: str) -> tuple[str, ...]:
    loc = (locale or "en").strip().lower()
    return q.choices_ru if loc.startswith("ru") else q.choices_en


def question_by_id(qid: str) -> Optional[InterviewQuestion]:
    for q in QUESTIONS():
        if q.id == qid:
            return q
    return None
