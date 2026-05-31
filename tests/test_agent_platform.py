"""Тесты agent platform (этап 0)."""
from __future__ import annotations

import asyncio
from typing import Optional

import pytest

from shared.agent.tools import ToolRegistry, select_tools, tool
from shared.agent.types import AgentContext
from shared.agent.config import load_tools_config


@tool(category="balance", always=True)
async def sample_balance(ctx: AgentContext) -> str:
    """Возвращает баланс пользователя."""
    return "balance ok"


@tool(category="transactions")
async def sample_txn(ctx: AgentContext, days: Optional[int] = None) -> str:
    """Список транзакций за период."""
    return f"days={days}"


def test_tool_schema_required_param():
    reg = ToolRegistry()
    reg.register(sample_txn)
    schema = reg.schemas(["sample_txn"])[0]["function"]["parameters"]
    assert "days" in schema["properties"]
    assert "days" not in schema["required"]


def test_tool_always_in_select():
    reg = ToolRegistry()
    reg.register(sample_balance)
    reg.register(sample_txn)
    cfg = load_tools_config()
    selected = select_tools("привет", reg, categories=cfg["categories"], fallback_threshold=4)
    assert "sample_balance" in selected


def test_select_tools_keyword_match():
    reg = ToolRegistry()
    reg.register(sample_balance)
    reg.register(sample_txn)
    cats = {
        "transactions": {"keywords": ["потратил"], "tools": ["sample_txn"]},
    }
    selected = select_tools("потратил 500 на кофе", reg, categories=cats, fallback_threshold=4)
    assert "sample_txn" in selected
    assert "sample_balance" in selected


def test_select_tools_fallback_all():
    reg = ToolRegistry()
    reg.register(sample_balance)
    reg.register(sample_txn)
    selected = select_tools("абракадабра без ключей", reg, categories={}, fallback_threshold=4)
    assert set(selected) == {"sample_balance", "sample_txn"}


def test_tool_handler_runs():
    reg = ToolRegistry()
    reg.register(sample_txn)
    ctx = AgentContext(user_id=1, domain="finance", question="q", system_prompt="s")
    out = asyncio.run(reg.get("sample_txn").handler(ctx=ctx, days=7))
    assert out == "days=7"


def test_insights_store_threshold(tmp_path):
    from shared.memory.insights import InsightsStore

    store = InsightsStore(tmp_path / "memory.db")
    p = "HRV<40 → переедание на следующий день"
    assert store.record_candidates(1, "finance", [p]) == []  # 1-е подтверждение
    assert store.record_candidates(1, "finance", [p]) == []  # 2-е
    pushable = store.record_candidates(1, "finance", [p])     # 3-е → порог
    assert len(pushable) == 1
    pid = pushable[0][0]
    assert store.read_confirmed(1, "finance") == []
    assert store.confirm(pid) is True
    assert store.read_confirmed(1, "finance") == [p]


def test_insights_reject(tmp_path):
    from shared.memory.insights import InsightsStore

    store = InsightsStore(tmp_path / "memory.db")
    store.record_candidates(2, "planning", ["паттерн X"])
    pending = store.list_pending(2, "planning")
    assert len(pending) == 1
    assert store.reject(pending[0]["id"]) is True
    assert store.list_pending(2, "planning") == []


def test_resolve_domain_multi_fixed(monkeypatch):
    from shared.agent.routing import resolve_domain
    from shared.agent.types import Domain

    monkeypatch.setenv("DEPLOY_MODE", "multi")
    monkeypatch.setenv("AGENT_DOMAIN", "finance")
    assert resolve_domain("сколько потратил на еду") == Domain.FINANCE


def test_resolve_domain_single_raises(monkeypatch):
    from shared.agent.routing import resolve_domain

    monkeypatch.setenv("DEPLOY_MODE", "single")
    monkeypatch.delenv("AGENT_DOMAIN", raising=False)
    with pytest.raises(RuntimeError, match="classify_host_domain_llm"):
        resolve_domain("привет")


def test_session_sqlite_persist(tmp_path, monkeypatch):
    from shared.memory import session as sess

    db = tmp_path / "mem.db"
    monkeypatch.setenv("AGENT_MEMORY_DB", str(db))
    monkeypatch.setenv("MEMORY_SESSION_PERSIST", "1")
    monkeypatch.setenv("MEMORY_SESSION_MIGRATE_PLANNING", "0")
    sess._store.clear()
    sess._sqlite_ready = False

    sess.append_turn(42, "finance", "user", "привет")
    sess.append_turn(42, "finance", "assistant", "ответ")
    sess._store.clear()

    hist = sess.get_history(42, "finance")
    assert len(hist) == 2
    assert hist[0].content == "привет"


def test_build_system_prompt_layers():
    from shared.memory.base import build_system_prompt

    class _Layer:
        def __init__(self, txt):
            self._txt = txt

        async def read(self, ctx):
            return self._txt

        async def write(self, ctx, turn):
            pass

    ctx = AgentContext(user_id=1, domain="finance", question="q", system_prompt="")
    out = asyncio.run(build_system_prompt("BASE", ctx, [_Layer("## A\nx"), _Layer("")]))
    assert out == "BASE\n\n## A\nx"


def test_finance_reply_menu_covers_nlu_config():
    from bot.config_loader import get_nlu_config, nlu_menu_buttons
    from bot.reply_menu import reply_menu_handlers

    cfg = get_nlu_config()
    handlers = reply_menu_handlers()
    assert nlu_menu_buttons(cfg) <= set(handlers)


def test_pick_host_domain_uses_llm(monkeypatch):
    from shared.telegram.host import agent as host_agent

    class _App:
        def has_domain(self, name: str) -> bool:
            return name in ("finance", "planning")

        def domains(self) -> list[str]:
            return ["finance", "planning"]

    async def _fake(text, **kwargs):
        return "planning"

    monkeypatch.setenv("DEPLOY_MODE", "single")
    monkeypatch.setattr(host_agent, "classify_host_domain_llm", _fake)
    out = asyncio.run(
        host_agent.pick_host_domain("привет", "auto", None, _App(), chat_id=1)
    )
    assert out == "planning"


def test_global_insights_in_all_domains(tmp_path, monkeypatch):
    from shared.memory.constants import GLOBAL_DOMAIN
    from shared.memory.insights import InsightsStore

    db = tmp_path / "memory.db"
    monkeypatch.setenv("AGENT_MEMORY_DB", str(db))
    store = InsightsStore(db)
    store.record_candidates(1, GLOBAL_DOMAIN, ["сплю мало → прокрастинация"])
    pending = store.list_pending(1, GLOBAL_DOMAIN)
    assert store.confirm(pending[0]["id"])
    assert store.read_confirmed(1, GLOBAL_DOMAIN) == ["сплю мало → прокрастинация"]
    assert store.read_confirmed(1, "finance") == []


def test_build_memory_layers_order(tmp_path, monkeypatch):
    from shared.agent.types import AgentContext
    from shared.memory.base import build_system_prompt
    from shared.memory.layers import build_memory_layers
    from shared.memory.constants import GLOBAL_DOMAIN
    from shared.memory.insights import InsightsStore

    agent_dir = tmp_path / "config" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "memory.yaml").write_text(
        "global_profile: user_profile.md\ninsights: {global_limit: 5, domain_limit: 3}\n",
        encoding="utf-8",
    )
    (agent_dir / "user_profile.md").write_text("Я — тест", encoding="utf-8")
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    monkeypatch.setenv("AGENT_MEMORY_DB", str(tmp_path / "mem.db"))
    from shared.memory import config as mem_cfg

    mem_cfg.load_memory_config.cache_clear()
    mem_cfg.load_memory_config()

    store = InsightsStore(tmp_path / "mem.db")
    store.record_candidates(9, GLOBAL_DOMAIN, ["глобальный паттерн"])
    pid = store.list_pending(9, GLOBAL_DOMAIN)[0]["id"]
    store.confirm(pid)

    ctx = AgentContext(user_id=9, domain="knowledge", question="q", system_prompt="")
    layers = build_memory_layers("knowledge")
    out = asyncio.run(build_system_prompt("BASE", ctx, layers))
    assert "BASE" in out
    assert "Я — тест" in out
    assert "глобальный паттерн" in out


def test_memory_tools_cross_domain_dialogue(tmp_path, monkeypatch):
    from shared.memory import session as sess
    from shared.agent.memory_tools import get_dialogue_history
    from shared.agent.types import AgentContext

    sess._store.clear()
    monkeypatch.setenv("MEMORY_SESSION_PERSIST", "0")
    sess.append_turn(5, "finance", "user", "баланс?")
    sess.append_turn(5, "planning", "user", "задачи?")

    ctx = AgentContext(user_id=5, domain="finance", question="q", system_prompt="")
    out = asyncio.run(get_dialogue_history(ctx=ctx, domain="planning", limit=4))
    assert "planning" in out
    assert "задачи" in out


def test_format_insights_lists_pending(tmp_path, monkeypatch):
    from shared.memory.insights import InsightsStore, get_store
    from shared.memory.layers import format_insights_text

    db = tmp_path / "memory.db"
    monkeypatch.setenv("AGENT_MEMORY_DB", str(db))
    get_store.cache_clear()
    store = InsightsStore(db)
    store.record_candidates(3, "finance", ["кандидат тест"])
    out = format_insights_text(3, scope="current", current_domain="finance")
    assert "кандидат" in out
    assert "/memory" in out


def test_attach_memory_tools_on_finance_registry():
    from bot.agent_tools import build_finance_registry

    reg = build_finance_registry()
    for name in ("get_user_profile", "get_user_insights", "get_dialogue_history"):
        assert name in reg.names()


def test_clear_all_history(tmp_path, monkeypatch):
    from shared.memory import session as sess

    monkeypatch.setenv("MEMORY_SESSION_PERSIST", "0")
    sess._store.clear()
    sess.append_turn(1, "finance", "user", "a")
    sess.append_turn(1, "planning", "user", "b")
    sess.clear_all_history(1)
    assert sess.get_history(1, "finance") == []
    assert sess.get_history(1, "planning") == []


def test_reply_keyboard_extras():
    from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

    from planning_bot.app import keyboards as pk
    from shared.telegram.keyboards import ReplyKeyboardExtras

    base = ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="A")]],
        resize_keyboard=True,
    )
    extras = ReplyKeyboardExtras()
    assert extras.apply(base) is base

    extras.set([[KeyboardButton(text="🏠 Главное")]])
    merged = extras.apply(base)
    assert any(b.text == "🏠 Главное" for row in merged.keyboard for b in row)

    pk.clear_keyboard_extras()
    kb = pk.get_main_keyboard()
    assert all(b.text != "🏠 Главное" for row in kb.keyboard for b in row)

    pk.set_keyboard_extras([[KeyboardButton(text="🏠 Главное")]])
    kb2 = pk.get_main_keyboard()
    assert any(b.text == "🏠 Главное" for row in kb2.keyboard for b in row)
    pk.clear_keyboard_extras()
