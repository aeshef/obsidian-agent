"""Slim reply keyboards after agent-first UX."""
from __future__ import annotations

from bot.config_loader import get_nlu_config, nlu_menu_buttons
from bot.menu_labels import finance_menu_texts
from bot.reply_menu import is_reply_menu_button, reply_menu_handlers
from planning_bot.app import keyboards as pb_kb
from planning_bot.app.menu_labels import (
    clear_menu_label_cache,
    is_planning_menu_button,
    main_menu_buttons,
    submenu_buttons,
)
from planning_bot.core.pdmsg import pdmsg


def test_finance_reply_menu_slim():
    t = finance_menu_texts()
    handlers = reply_menu_handlers()
    assert set(handlers) >= {
        t["balance"],
        t["last_ops"],
    }
    assert t["invest"] not in handlers
    assert t["plan"] not in handlers
    for legacy in ("add_expense", "summary", "sync"):
        if legacy in t:
            assert t[legacy] not in handlers
            assert not is_reply_menu_button(t[legacy])
    assert is_reply_menu_button(t["balance"])
    assert nlu_menu_buttons(get_nlu_config()) <= set(handlers)


def test_planning_main_keyboard_from_ui_capabilities():
    from shared.capabilities.menu_actions_config import clear_menu_actions_cache
    from shared.capabilities.profile import clear_capabilities_cache
    from shared.capabilities.ui_bindings import clear_ui_bindings_cache
    from shared.domain_messages import clear_domain_messages_cache
    from planning_bot.services.planning_text_triggers import clear_planning_text_triggers_cache

    clear_capabilities_cache()
    clear_ui_bindings_cache()
    clear_domain_messages_cache()
    clear_menu_actions_cache()
    clear_planning_text_triggers_cache()
    clear_menu_label_cache()
    pb_kb.clear_keyboard_extras()
    labels = {btn.text for row in pb_kb.get_main_keyboard().keyboard for btn in row}
    assert labels == main_menu_buttons()
    assert is_planning_menu_button(pdmsg("auto_ca15d9d2aa"))
    assert is_planning_menu_button(pdmsg("auto_e3bbb7b586"))
    assert not is_planning_menu_button(pdmsg("auto_32ec6c2753"))
    assert pdmsg("auto_edc1040220") in submenu_buttons()
    assert len(main_menu_buttons()) >= 2
