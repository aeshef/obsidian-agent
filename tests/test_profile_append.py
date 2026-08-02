"""Profile append propose/confirm (gitignored profile file)."""
from __future__ import annotations

import asyncio
from pathlib import Path

from shared.agent.types import AgentContext
from shared.memory import profile_append as pa


def test_propose_confirm_writes_section(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("AGENT_MEMORY_DB", str(tmp_path / "m.db"))
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    agent = tmp_path / "config" / "agent"
    agent.mkdir(parents=True)
    (agent / "memory.yaml").write_text(
        'global_profile: user_profile.md\n'
        'profile_append:\n  section_header: "## Agent notes"\n  max_chars: 200\n',
        encoding="utf-8",
    )
    from shared.memory.config import load_memory_config

    load_memory_config.cache_clear()
    pa._ready = False

    pid, body = pa.propose(3, "prefers short answers")
    assert pid and "short" in body
    ok, name = pa.confirm(3, pid)
    assert ok
    path = agent / "user_profile.md"
    text = path.read_text(encoding="utf-8")
    assert "## Agent notes" in text
    assert "prefers short answers" in text


def test_memory_tools_profile_roundtrip(tmp_path: Path, monkeypatch):
    from shared.agent import memory_tools as mt

    monkeypatch.setenv("AGENT_MEMORY_DB", str(tmp_path / "m.db"))
    monkeypatch.setenv("AGENT_ROOT", str(tmp_path))
    agent = tmp_path / "config" / "agent"
    agent.mkdir(parents=True)
    (agent / "memory.yaml").write_text(
        "global_profile: user_profile.md\nprofile_append:\n  section_header: '## Agent notes'\n",
        encoding="utf-8",
    )
    from shared.memory.config import load_memory_config

    load_memory_config.cache_clear()
    pa._ready = False
    ctx = AgentContext(user_id=4, domain="finance", question="q", system_prompt="")
    out = asyncio.run(mt.propose_profile_append(ctx, text="likes charts"))
    assert "id=" in out
    # extract id
    import re

    m = re.search(r"id=(\d+)", out)
    assert m
    conf = asyncio.run(mt.confirm_profile_append(ctx, pending_id=int(m.group(1))))
    assert "user_profile" in conf or "Appended" in conf or "Добавлено" in conf
