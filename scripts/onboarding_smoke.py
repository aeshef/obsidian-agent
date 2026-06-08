#!/usr/bin/env python3
"""Smoke-check enabled modules/connectors after onboarding (no Telegram, no secrets)."""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_env() -> None:
    env = _ROOT / ".env"
    if not env.is_file():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key = key.strip()
        if key and key not in os.environ:
            os.environ[key] = val.strip().strip('"').strip("'")


def _verify_connectors_all(
    errors: list[str], warnings: list[str], *, strict_env: bool, strict_files: bool
) -> None:
    from shared.capabilities.onboarding_verify import verify_enabled_connectors

    e, w = verify_enabled_connectors(strict_env=strict_env, strict_files=strict_files)
    errors.extend(e)
    warnings.extend(w)


def _golden_finance_check(errors: list[str]) -> None:
    """Assert finance-only preset disables planning module and optional connectors."""
    from shared.capabilities.presets import PRESET_FINANCE_ONLY, preset_document
    from shared.capabilities.profile import (
        CONNECTOR_APPLE_CALENDAR,
        CONNECTOR_APPLE_HEALTH,
        CONNECTOR_BROKER_SYNC,
        CONNECTOR_CORPORATE_BADGE,
        CONNECTOR_GMAIL_HEALTH,
        CONNECTOR_MAC_CONTEXT,
        MODULE_FINANCE,
        MODULE_KNOWLEDGE,
        MODULE_PLANNING,
        profile_from_document,
    )
    from shared.capabilities.sync_steps import (
        STEP_FINANCE_DASHBOARD,
        STEP_PLANNING_CHARTS,
        sync_step_enabled,
    )

    prof = profile_from_document(preset_document(PRESET_FINANCE_ONLY))
    if not prof.module(MODULE_FINANCE):
        errors.append("golden finance: finance module should be on")
    if prof.module(MODULE_PLANNING):
        errors.append("golden finance: planning module should be off")
    if prof.module(MODULE_KNOWLEDGE):
        errors.append("golden finance: knowledge module should be off")
    if prof.connector(CONNECTOR_BROKER_SYNC):
        errors.append("golden finance: broker_sync connector should be off")
    for conn in (
        CONNECTOR_CORPORATE_BADGE,
        CONNECTOR_APPLE_HEALTH,
        CONNECTOR_GMAIL_HEALTH,
        CONNECTOR_APPLE_CALENDAR,
        CONNECTOR_MAC_CONTEXT,
    ):
        if prof.connector(conn):
            errors.append(f"golden finance: {conn} should be off")
    if not sync_step_enabled(STEP_FINANCE_DASHBOARD, prof):
        errors.append("golden finance: finance dashboard sync should be on")
    if sync_step_enabled(STEP_PLANNING_CHARTS, prof):
        errors.append("golden finance: planning charts sync should be off")


def _golden_planning_check(errors: list[str]) -> None:
    """Assert planning-only preset disables finance sync and broker connector."""
    from shared.capabilities.presets import PRESET_PLANNING_ONLY, preset_document
    from shared.capabilities.profile import CONNECTOR_BROKER_SYNC, MODULE_FINANCE, profile_from_document
    from shared.capabilities.sync_steps import STEP_FINANCE_DASHBOARD, sync_step_enabled

    prof = profile_from_document(preset_document(PRESET_PLANNING_ONLY))
    if sync_step_enabled(STEP_FINANCE_DASHBOARD, prof):
        errors.append("golden planning: finance dashboard sync should be off")
    if prof.module(MODULE_FINANCE):
        errors.append("golden planning: finance module should be off")
    if prof.connector(CONNECTOR_BROKER_SYNC):
        errors.append("golden planning: broker_sync connector should be off")


def _check_bot_import(errors: list[str]) -> None:
    try:
        import unified_bot.main  # noqa: F401
    except Exception as e:
        errors.append(f"import unified_bot.main failed: {e}")


def _agent_sanity(errors: list[str], warnings: list[str]) -> None:
    from shared.capabilities.onboarding_verify import (
        agent_registry_sanity,
        finance_registry_sanity,
    )
    from shared.capabilities.presets import (
        PRESET_FINANCE_ONLY,
        PRESET_PLANNING_ONLY,
        preset_document,
    )

    errors.extend(agent_registry_sanity(preset_document(PRESET_PLANNING_ONLY)))
    for line in finance_registry_sanity(preset_document(PRESET_FINANCE_ONLY)):
        if "import failed" in line:
            warnings.append(line)
        else:
            errors.append(line)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--require-env",
        action="store_true",
        help="Fail if enabled connector playbook env keys are empty",
    )
    parser.add_argument(
        "--verify-connectors",
        action="store_true",
        help="Strict connector config checks (badge.yaml, etc.)",
    )
    parser.add_argument(
        "--golden-planning",
        action="store_true",
        help="Validate planning-only profile shape (CI / docs golden path)",
    )
    parser.add_argument(
        "--golden-finance",
        action="store_true",
        help="Validate finance-only profile shape (CI / docs golden path)",
    )
    parser.add_argument(
        "--check-bot-import",
        action="store_true",
        help="Import unified_bot.main (needs deps / venv in dev)",
    )
    parser.add_argument(
        "--verify-all",
        action="store_true",
        help="Per-connector file checks (badge.yaml, broker_sync.yaml) for enabled connectors",
    )
    parser.add_argument(
        "--agent-sanity",
        action="store_true",
        help="Planning-only tool registry shape (no Telegram)",
    )
    parser.add_argument(
        "--complete",
        action="store_true",
        help="Fail unless full /setup checklist passes (secrets, slots, accounts, prompts)",
    )
    args = parser.parse_args()
    _load_env()

    from shared.capabilities.onboarding_catalog import PLAYBOOKS
    from shared.capabilities.profile import clear_capabilities_cache, get_capabilities

    clear_capabilities_cache()
    prof = get_capabilities()
    errors: list[str] = []
    warnings: list[str] = []

    for mod in prof.enabled_modules():
        if mod == "finance" and not (os.environ.get("VAULT_PATH") or "").strip():
            errors.append("finance: VAULT_PATH missing in .env")
        if mod == "knowledge" and not (os.environ.get("TELEGRAM_USER_ID") or "").strip():
            warnings.append("knowledge: TELEGRAM_USER_ID empty (ingest may be limited)")

    for pb in PLAYBOOKS:
        if not prof.module(pb.module) or not prof.connector(pb.id):
            continue
        for key in pb.env_keys:
            if not (os.environ.get(key) or "").strip():
                msg = f"{pb.id}: env {key} not set"
                if args.require_env:
                    errors.append(msg)
                else:
                    warnings.append(msg)

    if args.verify_all or args.verify_connectors:
        _verify_connectors_all(
            errors,
            warnings,
            strict_env=args.require_env,
            strict_files=True,
        )
    elif args.require_env:
        _verify_connectors_all(errors, warnings, strict_env=True, strict_files=False)

    if args.golden_planning:
        _golden_planning_check(errors)
    if args.golden_finance:
        _golden_finance_check(errors)

    if args.agent_sanity:
        _agent_sanity(errors, warnings)

    if args.check_bot_import:
        _check_bot_import(errors)

    if args.complete:
        from shared.capabilities.onboarding_completion import completion_report

        ce, cw = completion_report(strict_interview=True)
        errors.extend(ce)
        warnings.extend(cw)

    from shared.capabilities.sync_steps import export_shell_env

    print(export_shell_env())
    print("modules:", prof.enabled_modules())
    print("connectors on:", [c for c in prof.connectors if prof.connector(c)])

    if warnings:
        print("\nWarnings:")
        for w in warnings:
            print(" ", w)
    if errors:
        print("\nErrors:")
        for e in errors:
            print(" ", e)
        return 1
    print("\nOK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
