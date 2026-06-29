"""host_domain router when LLM picks a disabled module."""
from __future__ import annotations

import asyncio

from shared.agent import llm_classify


def test_host_domain_planning_disabled_falls_back_to_general(monkeypatch):
    async def _fake(system, payload, *, label):
        return {"domain": "planning", "confidence": 0.9}

    monkeypatch.setattr(llm_classify, "_chat_json_classify", _fake)
    monkeypatch.setattr(llm_classify, "_load_prompt_file", lambda _n: "sys")
    out = asyncio.run(
        llm_classify.classify_host_domain_llm(
            "создай задачу починить молнию",
            enabled=["finance", "knowledge"],
        )
    )
    assert out == "general"


def test_host_domain_salvaged_paths_falls_back_to_general(monkeypatch):
    async def _fake(system, payload, *, label):
        return {"paths": ["Вопрос про свидание — совет/выбор"], "_salvaged": True}

    monkeypatch.setattr(llm_classify, "_chat_json_classify", _fake)
    monkeypatch.setattr(llm_classify, "_load_prompt_file", lambda _n: "sys")
    out = asyncio.run(
        llm_classify.classify_host_domain_llm(
            "куда девушку сводить на свидание вечером?",
            enabled=["finance", "planning", "knowledge"],
        )
    )
    assert out == "general"
