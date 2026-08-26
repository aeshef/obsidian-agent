"""Human-readable onboarding status — one checklist for wizard, /setup, DIY."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from shared.agent.config import agent_config_dir
from shared.capabilities.onboarding_catalog import playbooks_for_module
from shared.capabilities.onboarding_completion import completion_report
from shared.capabilities.onboarding_interview import iter_visible_questions
from shared.capabilities.profile import (
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    CapabilityProfile,
    get_capabilities,
)
from shared.setup.env_secrets import validate_core_secrets
from shared.yaml_config import load_yaml

_REPO = Path(__file__).resolve().parents[2]

# Concrete OS / external steps (never auto-granted)
_OS_STEPS = (
    ("macos_fda", "macOS Full Disk Access for Terminal/iTerm if Mac↔VPS sync or vault under ~/Documents"),
    ("obsidian_plugins", "Obsidian: enable community plugins from vault .obsidian/community-plugins.json"),
    ("botfather", "Telegram: @BotFather → /newbot → paste token when asked"),
    ("deepseek", "DeepSeek: platform.deepseek.com → API key"),
    ("openrouter", "OpenRouter (knowledge vision): openrouter.ai → API key"),
    ("gmail_app_password", "Gmail App Password only if gmail_health_pipeline connector is on"),
)


@dataclass(frozen=True)
class StatusItem:
    id: str
    ok: bool
    detail: str
    required: bool = True


def _env_ok(key: str) -> bool:
    return bool((os.environ.get(key) or "").strip())


def _load_state() -> dict:
    path = agent_config_dir() / "onboarding_state.yaml"
    if not path.is_file():
        return {}
    data = load_yaml(path, default={}) or {}
    return data if isinstance(data, dict) else {}


def enabled_bots(prof: CapabilityProfile) -> list[str]:
    """Venv components needed for this profile (finance_bot always for shared deps)."""
    bots = ["finance_bot"]  # shared PyYAML / smoke host
    if prof.module(MODULE_PLANNING):
        bots.append("planning_bot")
    if prof.module(MODULE_KNOWLEDGE):
        bots.append("knowledge_bot")
    # dedupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for b in bots:
        if b not in seen:
            seen.add(b)
            out.append(b)
    return out


def golden_smoke_flags(prof: CapabilityProfile) -> list[str]:
    flags: list[str] = []
    if prof.module(MODULE_PLANNING):
        flags.append("--golden-planning")
    if prof.module(MODULE_FINANCE):
        flags.append("--golden-finance")
    if prof.module(MODULE_KNOWLEDGE):
        flags.append("--golden-knowledge")
    return flags


def connector_instructions(prof: CapabilityProfile) -> list[str]:
    lines: list[str] = []
    for mod in (MODULE_FINANCE, MODULE_PLANNING, MODULE_KNOWLEDGE):
        if not prof.module(mod):
            continue
        for pb in playbooks_for_module(mod):
            if not prof.connector(pb.id):
                continue
            lines.append(f"[{pb.id}] {pb.cli_flag}")
            for step in pb.user_steps:
                lines.append(f"  - {step}")
            if pb.env_keys:
                lines.append(f"  - env: {', '.join(pb.env_keys)}")
    return lines


def os_checklist(prof: CapabilityProfile) -> list[tuple[str, str]]:
    steps = [
        _OS_STEPS[2],  # botfather
        _OS_STEPS[3],  # deepseek
        _OS_STEPS[1],  # obsidian
    ]
    if prof.module(MODULE_KNOWLEDGE):
        steps.append(_OS_STEPS[4])
    if prof.connector("gmail_health_pipeline"):
        steps.append(_OS_STEPS[5])
    if prof.connector("mac_context") or prof.connector("apple_health") or prof.connector("apple_calendar"):
        steps.append(_OS_STEPS[0])
    return steps


def collect_status(
    profile: Optional[CapabilityProfile] = None,
    *,
    locale: str | None = None,
) -> dict:
    """Structured status for CLI / Cursor."""
    from shared.locale import agent_locale

    loc = (locale or agent_locale() or "en").strip().lower()
    if loc.startswith("ru"):
        loc = "ru"
    else:
        loc = "en"

    cap_path = agent_config_dir() / "capabilities.yaml"
    if cap_path.is_file():
        prof = profile or get_capabilities()
    else:
        # Without capabilities, report as not started — avoid loading OSS starter as "truth"
        from shared.capabilities.presets import PRESET_PLANNING_ONLY, preset_document
        from shared.capabilities.profile import profile_from_document

        prof = profile or profile_from_document(preset_document(PRESET_PLANNING_ONLY))

    errors, warnings = completion_report(
        prof, locale=loc, strict_interview=False, validate_secrets=False
    )
    se, sw = validate_core_secrets(
        ping_deepseek_api=False,
        require_openrouter=False,
    )

    state = _load_state()
    next_qs = []
    if cap_path.is_file():
        for phase in ("intro", "before_layout", "after_layout", "after_secrets", "finalize"):
            for q in iter_visible_questions(prof, phase=phase, locale=loc, state=state):
                next_qs.append({"id": q.id, "phase": q.phase, "prompt": q.prompt_en if loc == "en" else q.prompt_ru})
                if len(next_qs) >= 3:
                    break
            if len(next_qs) >= 3:
                break

    items: list[StatusItem] = [
        StatusItem("capabilities", cap_path.is_file(), str(cap_path.relative_to(_REPO)) if cap_path.is_file() else "missing — apply playbook"),
        StatusItem("vault_path", _env_ok("VAULT_PATH"), os.environ.get("VAULT_PATH") or "unset"),
        StatusItem("telegram", _env_ok("TELEGRAM_UNIFIED_BOT_TOKEN") or _env_ok("TELEGRAM_BOT_TOKEN"), "set" if (_env_ok("TELEGRAM_UNIFIED_BOT_TOKEN") or _env_ok("TELEGRAM_BOT_TOKEN")) else "missing"),
        StatusItem("deepseek", _env_ok("DEEPSEEK_API_KEY"), "set" if _env_ok("DEEPSEEK_API_KEY") else "missing"),
    ]
    if prof.module(MODULE_KNOWLEDGE):
        items.append(
            StatusItem(
                "openrouter",
                _env_ok("OPENROUTER_API_KEY"),
                "set" if _env_ok("OPENROUTER_API_KEY") else "needed for vision/ingest",
            )
        )
    if prof.module(MODULE_FINANCE) or prof.module(MODULE_KNOWLEDGE):
        items.append(
            StatusItem(
                "telegram_user_id",
                _env_ok("TELEGRAM_USER_ID") or bool(str(state.get("telegram_id") or "").isdigit()),
                os.environ.get("TELEGRAM_USER_ID") or state.get("telegram_id") or "ask after bot /start",
            )
        )

    modules = {
        MODULE_FINANCE: prof.module(MODULE_FINANCE),
        MODULE_PLANNING: prof.module(MODULE_PLANNING),
        MODULE_KNOWLEDGE: prof.module(MODULE_KNOWLEDGE),
    }
    connectors = {c: prof.connector(c) for c in (
        "broker_sync", "corporate_badge", "manual_broker", "domestic_bank_cards",
        "apple_health", "gmail_health_pipeline", "apple_calendar", "mac_context",
        "knowledge_serendipity",
    ) if prof.connector(c)}

    return {
        "locale": loc,
        "capabilities_present": cap_path.is_file(),
        "modules": modules,
        "connectors_on": connectors,
        "bots": enabled_bots(prof),
        "golden_flags": golden_smoke_flags(prof),
        "items": items,
        "errors": errors + se,
        "warnings": warnings + sw,
        "next_questions": next_qs,
        "connector_steps": connector_instructions(prof),
        "os_checklist": [{"id": i, "text": t} for i, t in os_checklist(prof)],
        "bot_smoke_confirmed": bool(state.get("bot_smoke_confirmed")),
        "instruction": (
            "1) ./scripts/onboarding_wizard.sh --playbook planning|finance|knowledge|full\n"
            "2) Answer interview: ./scripts/oa-python.sh scripts/onboarding_interview.py next\n"
            "3) Secrets: ./scripts/oa-python.sh scripts/setup/env_tools.py set KEY 'value'\n"
            "4) Status: ./scripts/oa-python.sh scripts/onboarding_status.py\n"
            "5) Smoke: ./scripts/oa-python.sh scripts/onboarding_smoke.py --verify-all "
            + " ".join(golden_smoke_flags(prof))
            + "\n"
            "6) Run: ./scripts/run_unified_bot.sh → confirm-bot → finalize deploy"
        ),
    }


def format_status_text(data: dict) -> str:
    lines: list[str] = []
    lines.append("=== onboarding status ===")
    lines.append(f"locale: {data['locale']}")
    lines.append(
        "modules: "
        + ", ".join(f"{k}={'on' if v else 'off'}" for k, v in data["modules"].items())
    )
    if data["connectors_on"]:
        lines.append("connectors on: " + ", ".join(sorted(data["connectors_on"])))
    else:
        lines.append("connectors on: (none — optional flags only if you need them)")
    lines.append("venvs: " + " ".join(data["bots"]))
    lines.append("")
    for it in data["items"]:
        mark = "OK" if it.ok else "NEED"
        lines.append(f"  [{mark}] {it.id}: {it.detail}")
    if data["errors"]:
        lines.append("")
        lines.append("errors:")
        for e in data["errors"]:
            lines.append(f"  - {e}")
    if data["warnings"]:
        lines.append("")
        lines.append("warnings:")
        for w in data["warnings"][:12]:
            lines.append(f"  - {w}")
    if data["next_questions"]:
        lines.append("")
        lines.append("next interview:")
        for q in data["next_questions"]:
            lines.append(f"  - [{q['phase']}] {q['id']}: {q['prompt'][:100]}")
    if data["os_checklist"]:
        lines.append("")
        lines.append("external steps (you do these):")
        for step in data["os_checklist"]:
            lines.append(f"  - {step['text']}")
    if data["connector_steps"]:
        lines.append("")
        lines.append("enabled connector setup:")
        lines.extend(f"  {x}" for x in data["connector_steps"])
    lines.append("")
    lines.append("instructions:")
    for line in data["instruction"].splitlines():
        lines.append(f"  {line}")
    return "\n".join(lines) + "\n"
