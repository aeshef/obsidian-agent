"""Config-driven host menu detection."""
from __future__ import annotations

from shared.capabilities.profile import clear_capabilities_cache
from unified_bot.host.keyboards import root_keyboard
from unified_bot.host.menu_detection import clear_menu_detection_cache, is_finance_menu_text


def test_finance_menu_uses_reply_menu(monkeypatch):
    from planning_bot.core.pdmsg import pdmsg

    clear_menu_detection_cache()
    assert is_finance_menu_text(pdmsg("auto_ca15d9d2aa")) is False


def test_root_keyboard_hides_disabled_modules(monkeypatch):
    monkeypatch.setenv("CAP_MODULE_FINANCE", "0")
    monkeypatch.setenv("CAP_MODULE_KNOWLEDGE", "0")
    clear_capabilities_cache()
    kb = root_keyboard()
    labels = {btn.text for row in kb.keyboard for btn in row}
    assert not any("Finance" in t or "Финанс" in t for t in labels)
    clear_capabilities_cache()
