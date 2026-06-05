"""Reply/inline keyboards respect ui_capabilities gates."""
from __future__ import annotations

from bot.handlers.investments import invest_menu_kb
from bot.handlers.start import main_menu_inline
from planning_bot.app import keyboards as pb_kb
from planning_bot.core.pdmsg import pdmsg
from shared.capabilities.profile import clear_capabilities_cache
from shared.capabilities.ui_bindings import clear_ui_bindings_cache
from shared.i18n import clear_messages_cache
from shared.telegram.host.keyboards import knowledge_keyboard, root_keyboard


def _clear_caches() -> None:
    clear_capabilities_cache()
    clear_ui_bindings_cache()
    clear_messages_cache()


def test_routines_keyboard_empty_when_feature_off(monkeypatch):
    monkeypatch.setenv("CAP_FEATURE_PLANNING_ROUTINES", "0")
    _clear_caches()
    kb = pb_kb.get_routines_keyboard()
    labels = {btn.text for row in kb.keyboard for btn in row}
    assert pdmsg("auto_f317ab8f35") not in labels
    assert not any("Routine" in t or "рутин" in t.lower() for t in labels if t)
    _clear_caches()


def test_invest_inline_hidden_without_connectors(monkeypatch):
    monkeypatch.setenv("CAP_CONNECTOR_BROKER_SYNC", "0")
    monkeypatch.setenv("CAP_CONNECTOR_MANUAL_BROKER", "0")
    _clear_caches()
    kb = invest_menu_kb()
    labels = {btn.text for row in kb.inline_keyboard for btn in row}
    sync_labels = {t for t in labels if t and ("sync" in t.lower() or "синх" in t.lower())}
    assert not sync_labels
    _clear_caches()


def test_knowledge_keyboard_hidden_when_module_off(monkeypatch):
    monkeypatch.setenv("CAP_MODULE_KNOWLEDGE", "0")
    _clear_caches()
    kb = knowledge_keyboard()
    labels = {btn.text for row in kb.keyboard for btn in row}
    from knowledge_bot.app import kb_labels as kb_lbl

    assert kb_lbl.bulk_on() == ""
    assert kb_lbl.query_button() == ""
    from shared.telegram.host import labels as host_lbl

    assert labels == {host_lbl.back_home()}
    _clear_caches()


def test_root_keyboard_omits_disabled_modules(monkeypatch):
    monkeypatch.setenv("CAP_MODULE_FINANCE", "0")
    monkeypatch.setenv("CAP_MODULE_PLANNING", "1")
    monkeypatch.setenv("CAP_MODULE_KNOWLEDGE", "0")
    _clear_caches()
    kb = root_keyboard()
    labels = {btn.text for row in kb.keyboard for btn in row}
    from shared.telegram.host import labels as L

    assert L.mode_planning() in labels
    assert L.mode_finance() not in labels
    assert L.mode_knowledge() not in labels
    _clear_caches()


def test_main_menu_inline_no_invest_when_gated(monkeypatch):
    monkeypatch.setenv("CAP_CONNECTOR_BROKER_SYNC", "0")
    monkeypatch.setenv("CAP_CONNECTOR_MANUAL_BROKER", "0")
    _clear_caches()
    kb = main_menu_inline()
    callbacks = {btn.callback_data for row in kb.inline_keyboard for btn in row}
    assert "action:invest" not in callbacks
    _clear_caches()
