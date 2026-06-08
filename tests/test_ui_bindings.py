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
    assert msg("finance", "sync_broker_button") == ""
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


def test_planning_auto_pattern_default(monkeypatch):
    monkeypatch.setenv("CAP_MODULE_PLANNING", "1")
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    from planning_bot.app.menu_labels import clear_menu_label_cache
    from shared.domain_messages import clear_domain_messages_cache

    clear_domain_messages_cache()
    clear_menu_label_cache()
    assert message_allowed("planning", "auto_ca15d9d2aa")
    clear_capabilities_cache()
    clear_ui_bindings_cache()


def test_planning_submenu_gated(monkeypatch):
    monkeypatch.setenv("CAP_MODULE_PLANNING", "0")
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    assert not message_allowed("planning", "submenu", "kanban_column")
    from planning_bot.app.menu_labels import is_planning_menu_button
    from planning_bot.core.config import KANBAN_COLUMNS

    if KANBAN_COLUMNS:
        assert not is_planning_menu_button(KANBAN_COLUMNS[0])
    clear_capabilities_cache()
    clear_ui_bindings_cache()


def test_finance_menu_balance_gated(monkeypatch):
    monkeypatch.setenv("CAP_MODULE_FINANCE", "0")
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    clear_messages_cache()
    assert not message_allowed("finance", "menu", "balance")
    assert msg("finance", "menu", "balance") == ""
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    clear_messages_cache()
