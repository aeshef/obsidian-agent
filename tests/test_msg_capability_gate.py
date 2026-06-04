"""msg() hides strings via ui_capabilities.yaml bindings."""
from __future__ import annotations

from shared.capabilities.profile import clear_capabilities_cache
from shared.capabilities.ui_bindings import clear_ui_bindings_cache
from shared.i18n import clear_messages_cache, msg


def test_msg_broker_binding_off(monkeypatch):
    monkeypatch.setenv("CAP_CONNECTOR_BROKER_SYNC", "0")
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    clear_messages_cache()
    assert msg("finance", "sync_tinkoff_button") == ""
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    clear_messages_cache()
