"""Pattern rules in ui_capabilities.yaml."""
from __future__ import annotations

from shared.capabilities.profile import clear_capabilities_cache
from shared.capabilities.ui_bindings import cap_spec_for_path, clear_ui_bindings_cache
from shared.i18n import clear_messages_cache, msg


def test_pattern_finance_invest(monkeypatch):
    monkeypatch.setenv("CAP_CONNECTOR_BROKER_SYNC", "0")
    monkeypatch.setenv("CAP_CONNECTOR_MANUAL_BROKER_ACCOUNTS", "0")
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    clear_messages_cache()
    assert cap_spec_for_path("finance.invest_topup_amount") == "any:broker,manual_broker"
    assert msg("finance", "invest_topup_amount") == ""
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    clear_messages_cache()
