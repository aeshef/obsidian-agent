"""Finance UI/NLU gates — hide broker flows when connector is off."""
from __future__ import annotations

from shared.capabilities.profile import CONNECTOR_BROKER_SYNC, get_capabilities
from shared.i18n import msg_raw

# Message keys in config/messages.*.yaml (finance section), not literal button text.
_BROKER_EXACT_COMMAND_KEYS = (
    "exact_command_broker_sync",
    "exact_command_tinkoff_sync",  # legacy local yaml alias
)


def _broker_provider_active() -> bool:
    from shared.finance.broker_sync_config import broker_sync_provider

    return broker_sync_provider() != "none"


def broker_sync_enabled() -> bool:
    return get_capabilities().connector(CONNECTOR_BROKER_SYNC) and _broker_provider_active()


def filter_finance_exact_commands(commands: set[str]) -> set[str]:
    if broker_sync_enabled():
        return set(commands)
    drop = {msg_raw("finance", k) for k in _BROKER_EXACT_COMMAND_KEYS if msg_raw("finance", k)}
    return set(commands) - drop
