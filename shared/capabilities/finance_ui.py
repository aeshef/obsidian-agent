"""Finance Telegram UI gates."""
from __future__ import annotations

from shared.capabilities.finance_gates import broker_sync_enabled
from shared.capabilities.profile import CONNECTOR_MANUAL_BROKER, get_capabilities


def invest_menu_visible() -> bool:
    prof = get_capabilities()
    return broker_sync_enabled() or prof.connector(CONNECTOR_MANUAL_BROKER)


def domestic_cards_enabled() -> bool:
    from shared.capabilities.profile import CONNECTOR_DOMESTIC_BANK_CARDS

    return get_capabilities().connector(CONNECTOR_DOMESTIC_BANK_CARDS)
