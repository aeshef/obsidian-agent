"""Post-secret and agent sanity checks for guided onboarding (no Telegram API)."""
from __future__ import annotations

import os
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, Optional

import yaml

from shared.capabilities.onboarding_catalog import PLAYBOOKS, ConnectorPlaybook
from shared.capabilities.profile import (
    CONNECTOR_BROKER_SYNC,
    CONNECTOR_CORPORATE_BADGE,
    CONNECTOR_GMAIL_HEALTH,
    CONNECTOR_MANUAL_BROKER,
    CapabilityProfile,
    clear_capabilities_cache,
    get_capabilities,
    profile_from_document,
)

_REPO_[REDACTED]


@contextmanager
def temporary_capabilities_document(doc: dict) -> Iterator[CapabilityProfile]:
    """Load profile from dict via CAPABILITIES_PATH (tests / sanity)."""
    clear_capabilities_cache()
    old_path = os.environ.get("CAPABILITIES_PATH")
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8") as f:
        yaml.safe_dump(doc, f, allow_unicode=True, sort_keys=False)
        path = f.name
    os.environ["CAPABILITIES_PATH"] = path
    clear_capabilities_cache()
    try:
        yield get_capabilities()
    finally:
        clear_capabilities_cache()
        if old_path is None:
            os.environ.pop("CAPABILITIES_PATH", None)
        else:
            os.environ["CAPABILITIES_PATH"] = old_path
        clear_capabilities_cache()
        try:
            Path(path).unlink(missing_ok=True)
        except OSError:
            pass


def _badge_yaml_errors(*, strict: bool) -> list[str]:
    path = _REPO_ROOT / "finance_bot" / "config" / "badge.yaml"
    if not path.is_file():
        return ["corporate_badge: badge.yaml missing (apply --setup-badge)"] if strict else []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return [f"corporate_badge: invalid badge.yaml: {e}"]
    if not data.get("enabled"):
        return ["corporate_badge: set enabled: true in badge.yaml"]
    return []


def _broker_yaml_errors(*, strict: bool) -> list[str]:
    path = _REPO_ROOT / "finance_bot" / "config" / "broker_sync.yaml"
    if not path.is_file():
        return ["broker_sync: copy broker_sync.yaml.example → broker_sync.yaml"] if strict else []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as e:
        return [f"broker_sync: invalid broker_sync.yaml: {e}"]
    provider = str(data.get("provider") or "tinkoff").strip().lower()
    if provider == "none":
        return ["broker_sync: provider is none but connector is on"]
    return []


def verify_playbook(pb: ConnectorPlaybook, *, strict_env: bool, strict_files: bool) -> list[str]:
    errors: list[str] = []
    for key in pb.env_keys:
        if not (os.environ.get(key) or "").strip():
            if strict_env:
                errors.append(f"{pb.id}: env {key} not set")
    if pb.id == CONNECTOR_CORPORATE_BADGE and strict_files:
        errors.extend(_badge_yaml_errors(strict=True))
    if pb.id == CONNECTOR_BROKER_SYNC and strict_files:
        errors.extend(_broker_yaml_errors(strict=True))
    if pb.id == CONNECTOR_GMAIL_HEALTH and strict_env:
        for key in pb.env_keys:
            if not (os.environ.get(key) or "").strip():
                errors.append(f"{pb.id}: env {key} required for IMAP pipeline")
    return errors


def verify_enabled_connectors(
    profile: Optional[CapabilityProfile] = None,
    *,
    strict_env: bool = False,
    strict_files: bool = False,
) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for each enabled connector playbook."""
    prof = profile or get_capabilities()
    errors: list[str] = []
    warnings: list[str] = []
    for pb in PLAYBOOKS:
        if not prof.module(pb.module) or not prof.connector(pb.id):
            continue
        errs = verify_playbook(pb, strict_env=strict_env, strict_files=strict_files)
        for e in errs:
            (errors if strict_env or strict_files else warnings).append(e)
    return errors, warnings


def agent_registry_sanity(doc: dict) -> list[str]:
    """Planning-only profile must expose kanban tools, not health/broker tools."""
    errors: list[str] = []
    with temporary_capabilities_document(doc) as prof:
        if not prof.module("planning"):
            return ["agent_sanity: document must enable planning module"]
        from planning_bot.app.agent_tools import build_planning_registry

        names = set(build_planning_registry().names())
        required = {"get_kanban", "search_tasks", "apply_kanban_task", "get_action_log"}
        missing = required - names
        if missing:
            errors.append(f"agent_sanity: missing tools {sorted(missing)}")
        forbidden = {"get_health_snapshot", "get_calendar", "get_mac_context"}
        present = forbidden & names
        if present:
            errors.append(f"agent_sanity: planning-only must not expose {sorted(present)}")
    return errors


def finance_registry_sanity(doc: dict) -> list[str]:
    errors: list[str] = []
    with temporary_capabilities_document(doc) as prof:
        if not prof.module("finance"):
            return ["agent_sanity finance: document must enable finance module"]
        if prof.module("planning"):
            errors.append("agent_sanity finance: planning module should be off")
        fb_root = str(_REPO_ROOT / "finance_bot")
        if fb_root not in sys.path:
            sys.path.insert(0, fb_root)
        try:
            from finance_bot.bot.agent_tools import build_finance_registry
        except ImportError as e:
            return [f"agent_sanity finance: import failed: {e}"]
        names = set(build_finance_registry().names())
        forbidden = {"get_kanban", "apply_kanban_task", "get_health_snapshot", "get_calendar"}
        present = forbidden & names
        if present:
            errors.append(f"agent_sanity finance: must not expose {sorted(present)}")
        if "get_badge_status" in names:
            from shared.capabilities.registry import corporate_badge_runtime_enabled

            if not corporate_badge_runtime_enabled():
                errors.append("agent_sanity: get_badge_status registered but badge off")
        connectors = doc.get("connectors") or {}
        if not connectors.get(CONNECTOR_BROKER_SYNC) and not connectors.get(
            CONNECTOR_MANUAL_BROKER
        ):
            if "get_broker_overview" in names:
                errors.append("agent_sanity: no broker connectors but get_broker_overview present")
    return errors
