"""Slim reply keyboards after agent-first UX."""
from __future__ import annotations

from bot.config_loader import get_nlu_config, nlu_menu_buttons
from bot.menu_labels import finance_menu_texts
from bot.reply_menu import is_reply_menu_button, reply_menu_handlers
from planning_bot.app import keyboards as pb_kb
from planning_bot.app.menu_labels import MAIN_MENU_BUTTONS, SUBMENU_BUTTONS, is_planning_menu_button
from planning_bot.core.pdmsg import pdmsg


def test_finance_reply_menu_slim():
    t = finance_menu_texts()
    handlers = reply_menu_handlers()
    assert set(handlers) >= {
        t["invest"],
        t["balance"],
        t["last_ops"],
        t["plan"],
    }
    assert t["add_expense"] not in handlers
    assert t["summary"] not in handlers
    assert t["sync"] not in handlers
    assert not is_reply_menu_button(t["add_expense"])
    assert is_reply_menu_button(t["balance"])
    assert nlu_menu_buttons(get_nlu_config()) <= set(handlers)


def test_planning_main_keyboard_only_my_tasks():
    labels = {btn.text for row in pb_kb.get_main_keyboard().keyboard for btn in row}
    assert labels == {pdmsg("auto_ca15d9d2aa")}
    assert is_planning_menu_button(pdmsg("auto_ca15d9d2aa"))
    assert not is_planning_menu_button(pdmsg("auto_32ec6c2753"))
    assert not is_planning_menu_button(pdmsg("auto_f895d3042c"))
    assert pdmsg("auto_edc1040220") in SUBMENU_BUTTONS
    assert pdmsg("auto_f317ab8f35") not in SUBMENU_BUTTONS
    assert len(MAIN_MENU_BUTTONS) == 1
