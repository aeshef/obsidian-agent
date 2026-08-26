"""Telegram UX: menu-only domain dispatch + unified free text."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from unified_bot.host.domain_dispatch import try_dispatch_domain_text
from unified_bot.host.auto_dispatch import (
    _looks_like_txn_batch,
    _looks_like_txn_candidate,
    dispatch_auto_free_text,
)
from shared.telegram.push_format import format_push, format_push_sections
from shared.telegram import push_policy as pp


class _App:
    def __init__(self, domains=("finance", "planning", "knowledge")):
        self._domains = set(domains)

    def has_domain(self, name: str) -> bool:
        return name in self._domains

    def domains(self) -> list[str]:
        return sorted(self._domains)


def test_txn_candidate_prefilter():
    assert _looks_like_txn_candidate("coffee 300") is True
    assert _looks_like_txn_candidate("how much did I spend?") is False
    assert _looks_like_txn_candidate("what is on the board") is False
    bulk = (
        "20 июля перевод с уралсиба на jusan 60000р\n"
        "27 июля перевод с уралсиба на jusan 20000р\n"
        "2 августа перевод с уралсиба на jusan 20000р\n"
        "4 августа перевод с уралсиба на jusan 15000р\n"
        "4 августа лиза пополнила мне уралсиб на 10000\n"
        "5 августа перевел с уралсиба на jusan 30000р\n"
        "7 августа перевел с уралсиба на jusan 20000р"
    )
    assert len(bulk) > 160
    assert _looks_like_txn_candidate(bulk) is True
    assert _looks_like_txn_batch(bulk) is True
    assert _looks_like_txn_candidate("x" * 200) is False


def test_txn_batch_skips_intent_llm(monkeypatch):
    """Multi-line money dump must hit NLU confirm queue, not finance_query agent."""
    import sys
    import types

    called = {"nlu": 0, "llm": 0}

    async def _nlu(text, message, state):
        called["nlu"] += 1

    async def _llm(*a, **k):
        called["llm"] += 1
        return "finance_query"

    # Stub finance handlers so this test does not need finance_bot/.venv.
    bot_mod = types.ModuleType("bot")
    handlers_mod = types.ModuleType("bot.handlers")
    tx_mod = types.ModuleType("bot.handlers.transactions")
    tx_mod._process_transactions = _nlu
    monkeypatch.setitem(sys.modules, "bot", bot_mod)
    monkeypatch.setitem(sys.modules, "bot.handlers", handlers_mod)
    monkeypatch.setitem(sys.modules, "bot.handlers.transactions", tx_mod)
    monkeypatch.setattr(
        "shared.agent.llm_classify.classify_finance_intent_llm",
        _llm,
    )
    monkeypatch.setattr(
        "unified_bot.host.auto_dispatch.deliver_agent_answer",
        AsyncMock(),
    )
    monkeypatch.setattr(
        "unified_bot.host.auto_dispatch._try_knowledge_save",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "unified_bot.host.auto_dispatch.keyboard_for_mode",
        lambda *a, **k: None,
    )

    dump = (
        "11 августа (Яндекс Банк)\n"
        "−83р · Проезд метро\n"
        "−289р · Сигареты\n"
        "12 августа (Яндекс Банк)\n"
        "−600р · Аренда сервера\n"
        "−614р · Такси"
    )
    msg = MagicMock()
    msg.chat.id = 1
    msg.from_user.id = 1
    msg.bot = MagicMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"ui_mode": "auto"})

    asyncio.run(dispatch_auto_free_text(msg, state, _App(), dump))
    assert called["nlu"] == 1
    assert called["llm"] == 0


def test_domain_dispatch_ignores_pinned_free_text(monkeypatch):
    called = {"n": 0}

    async def _boom(*a, **k):
        called["n"] += 1
        return True

    monkeypatch.setattr(
        "unified_bot.host.domain_dispatch.DOMAIN_HANDLERS",
        {"finance": _boom, "planning": _boom, "knowledge": _boom},
    )
    monkeypatch.setattr(
        "unified_bot.host.domain_dispatch.is_finance_menu", lambda t: False
    )
    monkeypatch.setattr(
        "unified_bot.host.domain_dispatch.is_planning_menu", lambda t: False
    )
    monkeypatch.setattr(
        "unified_bot.host.domain_dispatch.is_knowledge_menu", lambda t: False
    )

    msg = MagicMock()
    state = AsyncMock()
    handled = asyncio.run(
        try_dispatch_domain_text(
            msg, state, _App(), "how much did I spend on food vs tasks", "finance"
        )
    )
    assert handled is False
    assert called["n"] == 0


def test_domain_dispatch_handles_menu_when_pinned(monkeypatch):
    async def _ok(*a, **k):
        return True

    monkeypatch.setattr(
        "unified_bot.host.domain_dispatch.DOMAIN_HANDLERS",
        {"finance": _ok},
    )
    monkeypatch.setattr(
        "unified_bot.host.domain_dispatch.is_finance_menu",
        lambda t: t == "MENU_FIN",
    )
    monkeypatch.setattr(
        "unified_bot.host.domain_dispatch.is_planning_menu", lambda t: False
    )
    monkeypatch.setattr(
        "unified_bot.host.domain_dispatch.is_knowledge_menu", lambda t: False
    )
    monkeypatch.setattr(
        "unified_bot.host.domain_dispatch.domain_routing_order",
        lambda: ("finance",),
    )

    msg = MagicMock()
    state = AsyncMock()
    handled = asyncio.run(
        try_dispatch_domain_text(msg, state, _App(("finance",)), "MENU_FIN", "finance")
    )
    assert handled is True


def test_free_text_goes_unified(monkeypatch):
    delivered = {}

    async def _deliver(bot, chat_id, agent_app, question, **kwargs):
        delivered.update(kwargs)
        delivered["question"] = question
        return MagicMock()

    monkeypatch.setattr(
        "unified_bot.host.auto_dispatch.deliver_agent_answer", _deliver
    )
    monkeypatch.setattr(
        "unified_bot.host.auto_dispatch._try_finance_transaction",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "unified_bot.host.auto_dispatch._try_knowledge_save",
        AsyncMock(return_value=False),
    )
    monkeypatch.setattr(
        "unified_bot.host.auto_dispatch.keyboard_for_mode",
        lambda *a, **k: None,
    )

    msg = MagicMock()
    msg.chat.id = 42
    msg.from_user.id = 42
    msg.bot = MagicMock()
    state = AsyncMock()
    state.get_data = AsyncMock(return_value={"ui_mode": "finance"})

    asyncio.run(dispatch_auto_free_text(msg, state, _App(), "charts for last week"))
    assert delivered.get("unified") is True
    assert delivered.get("question") == "charts for last week"


def test_push_format_envelope():
    out = format_push("Title", "Body line")
    assert out.startswith("# Title")
    assert "Body line" in out
    assert "────────" not in out
    assert "✦" not in out


def test_push_format_sections_skips_empty():
    out = format_push_sections(
        "Brief",
        [("A", "one"), ("B", ""), ("C", "two")],
    )
    assert "## A" in out and "one" in out
    assert "## C" in out and "two" in out
    assert "## B" not in out


def test_push_policy_defaults(monkeypatch, tmp_path):
    from shared.agent import platform_config as pc

    cfg = tmp_path / "platform.yaml"
    cfg.write_text(
        "push_policy:\n"
        "  quiet_hours:\n"
        "    start: 23\n"
        "    end: 7\n"
        "  morning_brief:\n"
        "    enabled: 1\n"
        "    hour: 8\n"
        "    minute: 15\n"
        "    include:\n"
        "      stuck: 1\n"
        "      deadlines: 1\n"
        "  routines_morning_hours: []\n"
        "  finance_txn_reminder:\n"
        "    only_if_no_txn_today: 1\n"
        "  finance_daily_insight:\n"
        "    enabled: 0\n"
        "  serendipity:\n"
        "    hour_start: 11\n"
        "    hour_end: 20\n"
        "host_ui:\n"
        "  show_auto_mode_button: 0\n"
        "  show_knowledge_query_button: 0\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(pc, "agent_config_dir", lambda: tmp_path)
    pc.load_platform_config.cache_clear()
    assert pp.morning_brief_enabled() is True
    assert pp.morning_brief_hour() == 8
    assert pp.separate_morning_routine_hours() == []
    assert pp.evening_routine_hours() == []
    assert pp.separate_stuck_alerts_enabled() is False
    assert pp.finance_txn_reminder_only_if_no_txn() is True
    assert pp.finance_daily_insight_enabled() is False
    assert pp.serendipity_hour_start() == 11
    assert pp.show_auto_mode_button() is False
    assert pp.show_knowledge_query_button() is False
    from datetime import datetime

    assert pp.in_quiet_hours(datetime(2026, 8, 2, 23, 30)) is True
    assert pp.in_quiet_hours(datetime(2026, 8, 2, 8, 0)) is False
    assert pp.in_quiet_hours(datetime(2026, 8, 2, 6, 0)) is True
    pc.load_platform_config.cache_clear()


def test_root_keyboard_hides_auto_by_default(monkeypatch, tmp_path):
    from shared.agent import platform_config as pc
    from shared.capabilities.profile import clear_capabilities_cache
    from unified_bot.host.keyboards import root_keyboard
    from unified_bot.host import labels as L

    cfg = tmp_path / "platform.yaml"
    cfg.write_text("host_ui:\n  show_auto_mode_button: 0\n", encoding="utf-8")
    monkeypatch.setattr(pc, "agent_config_dir", lambda: tmp_path)
    pc.load_platform_config.cache_clear()
    monkeypatch.setenv("CAP_MODULE_FINANCE", "1")
    monkeypatch.setenv("CAP_MODULE_PLANNING", "1")
    monkeypatch.setenv("CAP_MODULE_KNOWLEDGE", "1")
    clear_capabilities_cache()
    labels = {btn.text for row in root_keyboard().keyboard for btn in row}
    assert L.mode_auto() not in labels
    assert L.mode_finance() in labels
    pc.load_platform_config.cache_clear()
    clear_capabilities_cache()
