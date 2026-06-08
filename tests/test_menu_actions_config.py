"""menu_actions in ui_capabilities.yaml matches Python handler registries."""
from __future__ import annotations

from finance_bot.bot.menu_action_handlers import FINANCE_ACTION_IDS
from knowledge_bot.app.menu_action_handlers import KNOWLEDGE_ACTION_IDS
from planning_bot.app.menu_action_handlers import PLANNING_ACTION_IDS
from shared.capabilities.menu_actions_config import (
    menu_reply_specs,
    menu_reset_label_keys,
    menu_submenu_specs,
)


def test_planning_menu_actions_registry():
    actions = {str(s.get("action")) for s in menu_reply_specs("planning")}
    assert actions <= PLANNING_ACTION_IDS
    assert menu_reset_label_keys("planning")
    kinds = {str(s.get("kind")) for s in menu_submenu_specs("planning")}
    assert kinds == {"kanban_column", "category", "priority"}


def test_finance_menu_actions_registry():
    actions = {str(s.get("action")) for s in menu_reply_specs("finance")}
    assert actions <= FINANCE_ACTION_IDS


def test_knowledge_menu_actions_registry():
    actions = {str(s.get("action")) for s in menu_reply_specs("knowledge")}
    assert actions <= KNOWLEDGE_ACTION_IDS
