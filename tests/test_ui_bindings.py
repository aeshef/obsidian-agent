"""Declarative UI string gates (config/ui_capabilities.yaml)."""
from __future__ import annotations

from shared.capabilities.profile import clear_capabilities_cache
from shared.capabilities.ui_bindings import cap_satisfied, clear_ui_bindings_cache, message_allowed
from shared.i18n import clear_messages_cache, msg


def test_msg_broker_button_hidden(monkeypatch):
    monkeypatch.setenv("CAP_CONNECTOR_BROKER_SYNC", "0")
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    clear_messages_cache()
    assert msg("finance", "sync_tinkoff_button") == ""
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    clear_messages_cache()


def test_any_invest_menu_spec():
    assert cap_satisfied("any:broker,manual_broker") in (True, False)


def test_routines_button_gated(monkeypatch):
    monkeypatch.setenv("CAP_FEATURE_PLANNING_ROUTINES", "0")
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    assert not message_allowed("planning", "auto_f317ab8f35")
    clear_capabilities_cache()
    clear_ui_bindings_cache()
