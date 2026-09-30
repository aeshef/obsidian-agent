"""Bootstrap phase progress — one contract for wizard, /setup, and status."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from shared.agent.config import agent_config_dir
from shared.capabilities.onboarding_deploy import interview_incomplete_ids, iter_visible_questions
from shared.capabilities.profile import CapabilityProfile, get_capabilities
from shared.yaml_config import load_yaml

_REPO = Path(__file__).resolve().parents[2]

# Ordered stranger path (~30 min total). Minutes = typical remaining from this step.
PHASES: tuple[tuple[str, str, int], ...] = (
    ("repo_root", "Open agent repo root", 28),
    ("env_file", "Create .env from example", 27),
    ("venv_bootstrap", "Install Python deps (./scripts/setup.sh)", 25),
    ("playbook", "Choose playbook + write capabilities.yaml", 24),
    ("vault_path", "Set VAULT_PATH to Obsidian folder", 22),
    ("locale", "Set locale + materialize vault_paths", 20),
    ("interview_intro", "Personal interview (intro phase)", 18),
    ("vault_layout", "Create vault folders (init_vault_layout)", 15),
    ("setup_sh", "Scoped venvs + gated configs", 12),
    ("secrets", "Telegram bot token + LLM API key", 8),
    ("interview_after", "Balances / telegram_id (if finance)", 6),
    ("smoke", "onboarding_smoke golden path", 4),
    ("bot_live", "Run bot + confirm Telegram smoke", 2),
    ("finalize", "Deploy target + completion gate", 1),
)


@dataclass(frozen=True)
class PhaseStatus:
    id: str
    title: str
    ok: bool
    detail: str
    minutes_hint: int
    required: bool = True


def _env_ok(key: str) -> bool:
    return bool((os.environ.get(key) or "").strip())


def _placeholder_val(val: str) -> bool:
    low = (val or "").strip().lower()
    if not low:
        return True
    for bad in ("your_", "changeme", "replace", "sk-...", "example.com", "hostname"):
        if bad in low:
            return True
    return False


def _load_state() -> dict:
    path = agent_config_dir() / "onboarding_state.yaml"
    if not path.is_file():
        return {}
    data = load_yaml(path, default={}) or {}
    return data if isinstance(data, dict) else {}


def _check_phase(
    phase_id: str,
    prof: CapabilityProfile,
    locale: str,
    state: dict,
) -> tuple[bool, str]:
    if phase_id == "repo_root":
        ok = (_REPO / "unified_bot" / "main.py").is_file()
        return ok, str(_REPO) if ok else "missing unified_bot/main.py"
    if phase_id == "env_file":
        p = _REPO / ".env"
        return p.is_file(), str(p.relative_to(_REPO)) if p.is_file() else "copy .env.example"
    if phase_id == "venv_bootstrap":
        v = _REPO / "finance_bot" / ".venv" / "bin" / "python"
        return v.is_file(), "finance_bot/.venv ready" if v.is_file() else "run ./scripts/setup.sh"
    if phase_id == "playbook":
        p = agent_config_dir() / "capabilities.yaml"
        return p.is_file(), "capabilities.yaml" if p.is_file() else "run apply_capabilities_profile --write"
    if phase_id == "vault_path":
        vp = os.environ.get("VAULT_PATH") or ""
        if _placeholder_val(vp):
            return False, "unset — set before init_vault_layout"
        return Path(vp).expanduser().is_dir(), vp
    if phase_id == "locale":
        from shared.locale import agent_locale

        vp_yaml = _REPO / "config" / "vault_paths.yaml"
        loc = (agent_locale() or os.environ.get("AGENT_LOCALE") or "").strip()
        if not loc:
            return False, "AGENT_LOCALE missing in .env"
        if not vp_yaml.is_file():
            return False, "config/vault_paths.yaml missing — materialize_locale.py"
        return True, f"AGENT_LOCALE={loc}"
    if phase_id == "interview_intro":
        incomplete = [
            q
            for q in interview_incomplete_ids(prof, state, locale)
            if q in {x.id for x in iter_visible_questions(prof, phase="intro", locale=locale, state=state)}
        ]
        if incomplete:
            return False, f"remaining: {', '.join(incomplete[:4])}"
        return True, "intro complete"
    if phase_id == "vault_layout":
        vp = os.environ.get("VAULT_PATH") or ""
        if not vp or not Path(vp).expanduser().is_dir():
            return False, "VAULT_PATH not set"
        # Heuristic: at least one module folder from vault_paths exists
        vpaths = load_yaml(_REPO / "config" / "vault_paths.yaml", default={}) or {}
        folders = (vpaths.get("folders") or {}) if isinstance(vpaths, dict) else {}
        if not folders:
            return False, "vault_paths.yaml has no folders"
        vault = Path(vp).expanduser()
        created = sum(1 for seg in folders.values() if (vault / str(seg)).is_dir())
        if created == 0:
            return False, "run init_vault_layout.py"
        return True, f"{created}/{len(folders)} top folders present"
    if phase_id == "setup_sh":
        bots = ["finance_bot"]
        if prof.module("planning"):
            bots.append("planning_bot")
        if prof.module("knowledge"):
            bots.append("knowledge_bot")
        missing = [b for b in bots if not (_REPO / b / ".venv" / "bin" / "python").is_file()]
        if missing:
            return False, f"missing venv: {', '.join(missing)}"
        return True, "venvs ready"
    if phase_id == "secrets":
        tg = _env_ok("TELEGRAM_UNIFIED_BOT_TOKEN") or _env_ok("TELEGRAM_BOT_TOKEN")
        llm = _env_ok("LLM_API_KEY") or _env_ok("DEEPSEEK_API_KEY") or _env_ok("DEEPSEEK_API_TOKEN")
        parts = []
        if not tg:
            parts.append("TELEGRAM_UNIFIED_BOT_TOKEN")
        if not llm:
            parts.append("LLM_API_KEY")
        if prof.module("knowledge") and not _env_ok("OPENROUTER_API_KEY"):
            parts.append("OPENROUTER_API_KEY (knowledge)")
        if parts:
            return False, "missing: " + ", ".join(parts)
        return True, "core secrets set"
    if phase_id == "interview_after":
        incomplete = [
            q
            for q in interview_incomplete_ids(prof, state, locale)
            if q
            in {x.id for x in iter_visible_questions(prof, phase="after_secrets", locale=locale, state=state)}
        ]
        if incomplete:
            return False, f"remaining: {', '.join(incomplete[:4])}"
        return True, "after_secrets complete"
    if phase_id == "smoke":
        return True, "run onboarding_smoke.py --verify-all + golden flags"
    if phase_id == "bot_live":
        if state.get("bot_smoke_confirmed"):
            return True, "bot_smoke_confirmed"
        return False, "run bot → /start → onboarding_interview.py confirm-bot"
    if phase_id == "finalize":
        incomplete = [
            q
            for q in interview_incomplete_ids(prof, state, locale)
            if q
            in {x.id for x in iter_visible_questions(prof, phase="finalize", locale=locale, state=state)}
        ]
        if incomplete:
            return False, f"remaining: {', '.join(incomplete[:3])}"
        return True, "finalize complete"
    return False, "unknown phase"


def collect_progress(
    profile: Optional[CapabilityProfile] = None,
    *,
    locale: str = "en",
) -> dict:
    prof = profile or get_capabilities()
    loc = "ru" if (locale or "").strip().lower().startswith("ru") else "en"
    state = _load_state()
    phases: list[PhaseStatus] = []
    done = 0
    next_id: str | None = None
    eta = 0
    for pid, title, minutes in PHASES:
        ok, detail = _check_phase(pid, prof, loc, state)
        phases.append(PhaseStatus(pid, title, ok, detail, minutes))
        if ok:
            done += 1
        elif next_id is None:
            next_id = pid
            eta = minutes
    total = len(PHASES)
    pct = int(round(100 * done / total)) if total else 0
    return {
        "done": done,
        "total": total,
        "percent": pct,
        "next_phase": next_id,
        "eta_minutes": eta,
        "phases": phases,
    }


def format_progress_text(data: dict) -> str:
    lines = [
        f"progress: {data['done']}/{data['total']} ({data['percent']}%)",
    ]
    if data.get("next_phase"):
        lines.append(f"next: {data['next_phase']} (~{data['eta_minutes']} min left for stranger path)")
    lines.append("")
    for p in data["phases"]:
        mark = "OK" if p.ok else "…"
        lines.append(f"  [{mark}] {p.id}: {p.detail}")
    return "\n".join(lines) + "\n"
