"""Mac sync step plan — Python source of truth for which CAP_SYNC_* steps run."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from shared.capabilities.profile import CapabilityProfile, get_capabilities
from shared.capabilities.sync_steps import (
    STEP_CALENDAR,
    STEP_CROSS_ANALYTICS,
    STEP_FINANCE_DASHBOARD,
    STEP_GMAIL_HEALTH,
    STEP_HEALTH_ANALYTICS,
    STEP_KB_MAINTENANCE,
    STEP_MAC_IPHONE,
    STEP_NUTRITION,
    STEP_PLANNING_CHARTS,
    STEP_VAULT_AUDIT_HEAVY,
    sync_step_enabled,
)

# Stable order for logging / dry-run (matches historical shell order intent).
SYNC_STEP_ORDER: tuple[str, ...] = (
    STEP_MAC_IPHONE,
    STEP_GMAIL_HEALTH,
    STEP_CALENDAR,
    STEP_NUTRITION,
    STEP_HEALTH_ANALYTICS,
    STEP_CROSS_ANALYTICS,
    STEP_PLANNING_CHARTS,
    STEP_FINANCE_DASHBOARD,
    STEP_KB_MAINTENANCE,
    STEP_VAULT_AUDIT_HEAVY,
)


@dataclass(frozen=True)
class SyncStepPlan:
    step: str
    enabled: bool


def plan_sync_steps(profile: Optional[CapabilityProfile] = None) -> list[SyncStepPlan]:
    prof = profile or get_capabilities()
    return [
        SyncStepPlan(step=s, enabled=sync_step_enabled(s, prof)) for s in SYNC_STEP_ORDER
    ]


def enabled_sync_steps(profile: Optional[CapabilityProfile] = None) -> list[str]:
    return [p.step for p in plan_sync_steps(profile) if p.enabled]


def export_sync_plan_shell(profile: Optional[CapabilityProfile] = None) -> str:
    """Emit shell-friendly lines: CAP_SYNC_FOO=0|1 in plan order."""
    lines = []
    for p in plan_sync_steps(profile):
        lines.append(f"export {p.step}={'1' if p.enabled else '0'}")
    return "\n".join(lines) + ("\n" if lines else "")
