"""Core priors, situation HUD, and unified insight scope."""
from __future__ import annotations

import asyncio

from shared.agent.types import AgentContext
from shared.memory.constants import GLOBAL_DOMAIN
from shared.memory.insights import InsightsStore, get_store
from shared.memory.scope import insights_scope_for_host, resolve_insight_domain


def test_resolve_insight_domain_unified_to_global():
    assert resolve_insight_domain("unified") == GLOBAL_DOMAIN
    assert resolve_insight_domain("") == GLOBAL_DOMAIN
    assert resolve_insight_domain("finance") == "finance"


def test_insights_scope_unified_current_is_all():
    assert insights_scope_for_host("current", "unified") == "all"
    assert insights_scope_for_host("finance", "unified") == "finance"
    assert insights_scope_for_host("current", "planning") == "current"


def test_format_insights_unified_current_lists_all_domains(tmp_path, monkeypatch):
    from shared.memory.layers import format_insights_text

    db = tmp_path / "memory.db"
    monkeypatch.setenv("AGENT_MEMORY_DB", str(db))
    get_store.cache_clear()
    store = InsightsStore(db)
    store.record_candidates(1, "finance", [("transfers are not spend", "durable")])
    pid = store.list_pending(1, "finance")[0]["id"]
    assert store.confirm(pid)

    text = format_insights_text(1, scope="current", current_domain="unified")
    assert "transfers are not spend" in text
    assert "unknown" not in text.lower()


def test_core_priors_prefers_durable_and_caps(tmp_path, monkeypatch):
    from shared.memory import config as mem_cfg
    from shared.memory.core_priors import collect_core_prior_lines

    db = tmp_path / "memory.db"
    monkeypatch.setenv("AGENT_MEMORY_DB", str(db))
    get_store.cache_clear()
    mem_cfg.load_memory_config.cache_clear()

    agent_dir = tmp_path / "config" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "memory.yaml").write_text(
        "core:\n  max_lines: 2\ninsights:\n  global_limit: 8\n  domain_limit: 10\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    mem_cfg.load_memory_config.cache_clear()

    store = InsightsStore(db)
    store.record_candidates(3, "planning", [("study can wait", "durable")])
    store.record_candidates(3, "finance", [("coffee is fine", "durable")])
    store.record_candidates(3, "finance", [("august spike", "periodic")])
    for row in store.list_pending(3):
        store.confirm(row["id"])

    lines = collect_core_prior_lines(3)
    assert len(lines) == 2
    blob = "\n".join(lines)
    assert "august spike" not in blob
    assert "study can wait" in blob or "coffee is fine" in blob


def test_core_priors_layer_empty_without_confirmed(tmp_path, monkeypatch):
    from shared.memory.core_priors import CorePriorsMemory

    db = tmp_path / "memory.db"
    monkeypatch.setenv("AGENT_MEMORY_DB", str(db))
    get_store.cache_clear()
    InsightsStore(db)
    ctx = AgentContext(user_id=4, domain="unified", question="q", system_prompt="")
    text = asyncio.run(CorePriorsMemory().read(ctx))
    assert text == ""


def test_situation_fail_open(monkeypatch):
    from shared.memory import situation as sit

    monkeypatch.setattr(sit, "_calendar_block", lambda: "")
    monkeypatch.setattr(sit, "_wip_block", lambda: "")
    assert sit.collect_situation_text() == ""


def test_build_memory_layers_unified_attaches_core(monkeypatch, tmp_path):
    from shared.memory import config as mem_cfg
    from shared.memory.core_priors import CorePriorsMemory
    from shared.memory.layers import build_memory_layers
    from shared.memory.situation import SituationMemory

    agent_dir = tmp_path / "config" / "agent"
    agent_dir.mkdir(parents=True)
    (agent_dir / "user_profile.md").write_text("me", encoding="utf-8")
    (agent_dir / "memory.yaml").write_text(
        'global_profile: "user_profile.md"\n', encoding="utf-8"
    )
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    mem_cfg.load_memory_config.cache_clear()

    layers = build_memory_layers("unified", insights=False)
    types = {type(x) for x in layers}
    assert CorePriorsMemory in types
    assert SituationMemory in types
