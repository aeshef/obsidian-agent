"""Filter agent tools by capabilities manifest."""
from __future__ import annotations

from typing import Any, Callable, Iterable, Optional, Sequence

from shared.agent.tools import ToolRegistry
from shared.capabilities.profile import (
    CONNECTOR_APPLE_CALENDAR,
    CONNECTOR_APPLE_HEALTH,
    CONNECTOR_BROKER_SYNC,
    CONNECTOR_CORPORATE_BADGE,
    CONNECTOR_MANUAL_BROKER,
    CONNECTOR_MAC_CONTEXT,
    CapabilityProfile,
    MODULE_FINANCE,
    MODULE_KNOWLEDGE,
    MODULE_PLANNING,
    get_capabilities,
    module_enabled,
)

ConnectorGate = Optional[str]

FINANCE_TOOL_CONNECTORS: dict[str, ConnectorGate] = {
    "get_badge_status": CONNECTOR_CORPORATE_BADGE,
}

PLANNING_TOOL_CONNECTORS: dict[str, ConnectorGate] = {
    "get_health_snapshot": CONNECTOR_APPLE_HEALTH,
    "get_health_series": CONNECTOR_APPLE_HEALTH,
    "get_health_summary": CONNECTOR_APPLE_HEALTH,
    "get_health_anomalies": CONNECTOR_APPLE_HEALTH,
    "get_health_correlations": CONNECTOR_APPLE_HEALTH,
    "export_health_dataset": CONNECTOR_APPLE_HEALTH,
    "get_mac_context": CONNECTOR_MAC_CONTEXT,
    "get_mac_series": CONNECTOR_MAC_CONTEXT,
    "get_mac_snapshots": CONNECTOR_MAC_CONTEXT,
    "get_calendar": CONNECTOR_APPLE_CALENDAR,
    "get_calendar_analytics": CONNECTOR_APPLE_CALENDAR,
}


def _tool_name(tool: Any) -> str:
    return getattr(tool, "__name__", tool.__class__.__name__)


def _connector_allowed(profile: CapabilityProfile, connector: ConnectorGate) -> bool:
    if connector is None:
        return True
    return profile.connector(connector)


def filter_tools(
    tools: Sequence[Any],
    *,
    connector_map: dict[str, ConnectorGate],
    profile: Optional[CapabilityProfile] = None,
    extra_allow: Optional[Callable[[CapabilityProfile, Any], bool]] = None,
) -> list[Any]:
    prof = profile or get_capabilities()
    out: list[Any] = []
    for tool in tools:
        name = _tool_name(tool)
        conn = connector_map.get(name)
        if not _connector_allowed(prof, conn):
            continue
        if extra_allow is not None and not extra_allow(prof, tool):
            continue
        out.append(tool)
    return out


def corporate_badge_runtime_enabled() -> bool:
    """Alias for finance is_badge_enabled() when finance package is importable."""
    try:
        from bot.config_loader import is_badge_enabled

        return is_badge_enabled()
    except Exception:
        return get_capabilities().connector(CONNECTOR_CORPORATE_BADGE)


def _badge_runtime_ok(_prof: CapabilityProfile, _tool: Any) -> bool:
    return corporate_badge_runtime_enabled()


def _finance_extra_allow(prof: CapabilityProfile, tool: Any) -> bool:
    name = _tool_name(tool)
    if name == "get_broker_overview":
        return prof.connector(CONNECTOR_BROKER_SYNC) or prof.connector(CONNECTOR_MANUAL_BROKER)
    if name == "get_badge_status":
        return _badge_runtime_ok(prof, tool)
    return True


def filter_finance_tools(
    tools: Iterable[Any], profile: Optional[CapabilityProfile] = None
) -> list[Any]:
    prof = profile or get_capabilities()
    if not prof.module(MODULE_FINANCE):
        return []
    return filter_tools(
        list(tools),
        connector_map=FINANCE_TOOL_CONNECTORS,
        profile=prof,
        extra_allow=_finance_extra_allow,
    )


def _planning_extra_allow(prof: CapabilityProfile, tool: Any) -> bool:
    from shared.capabilities.planning_gates import planning_routines_enabled

    name = _tool_name(tool)
    if name == "get_routines_status":
        return planning_routines_enabled()
    return True


def filter_planning_tools(
    tools: Iterable[Any], profile: Optional[CapabilityProfile] = None
) -> list[Any]:
    prof = profile or get_capabilities()
    if not prof.module(MODULE_PLANNING):
        return []
    return filter_tools(
        list(tools),
        connector_map=PLANNING_TOOL_CONNECTORS,
        profile=prof,
        extra_allow=_planning_extra_allow,
    )


def register_tools(reg: ToolRegistry, tools: Iterable[Any]) -> None:
    reg.register_many(list(tools))


def knowledge_module_enabled() -> bool:
    return module_enabled(MODULE_KNOWLEDGE)
