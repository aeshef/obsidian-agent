"""Behavioral regressions for durable agent memory and execution, no live effects."""

import asyncio
import json
from pathlib import Path

import pytest

from shared.agent.tools import ToolRegistry, tool
from shared.agent.types import AgentContext, ToolCall
from shared.agent_runtime import followups, memory, operations
from shared.agent_runtime.db import connection


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("AGENT_MEMORY_DB", str(tmp_path / "memory.db"))
    import shared.agent_runtime.config as cfg

    monkeypatch.setattr(cfg, "agent_config_dir", lambda: Path(__file__).resolve().parents[1] / "config/agent")


def test_episode_search_survives_restart_and_isolates_users():
    memory.archive(1, "planning", "user", "Discussed robot clustering project")
    memory.archive(2, "finance", "user", "Private clustering investment")
    hits = memory.search(1, "clustering")
    assert len(hits) == 1 and hits[0]["user_id"] == 1
    assert memory.search(1, '" OR *') == []


def test_project_and_memory_correction_expiry_and_provenance():
    p = memory.project(1, "robot", "Build robot", ["note.md"])
    assert memory.project(1, "robot", "Build safely", ["note.md"])["id"] == p["id"]
    first = memory.record(1, "decision", "Use A", "user:1", "user_stated", p["id"])
    second = memory.record(1, "decision", "Use B", "user:2", "user_stated", p["id"], supersedes=first["id"])
    rows = memory.records(1, p["id"])
    assert len(rows) == 1 and rows[0]["id"] == second["id"] and rows[0]["source"] == "user:2"
    assert len(memory.records(1, p["id"], True)) == 2
    with pytest.raises(ValueError):
        memory.record(2, "fact", "secret", "user:3", supersedes=second["id"])
    memory.record(
        1,
        "fact",
        "expired",
        "source",
        "observed",
        valid_from="2020-01-01T00:00:00Z",
        valid_until="2020-02-01T00:00:00Z",
    )
    assert all(r["body"] != "expired" for r in memory.records(1))


def test_procedure_needs_explicit_review():
    p = memory.record(1, "procedure", "Check result before retry", "test:receipt", "observed")
    assert memory.records(1) == []
    assert not memory.review_record(2, p["id"], True)
    assert memory.review_record(1, p["id"], True)
    assert len(memory.records(1)) == 1


def test_mutation_deduplicated_and_unknown_not_retried():
    calls = []

    @tool(mutating=True)
    async def write(ctx):
        calls.append(1)
        return "ok"

    reg = ToolRegistry()
    reg.register(write)
    ctx = AgentContext(1, "general", "do it", "", extras={"request_key": "message:1"})
    tc = ToolCall("a", "write", {})
    asyncio.run(operations.execute(reg.get("write"), tc, ctx))
    result = json.loads(asyncio.run(operations.execute(reg.get("write"), tc, ctx)))
    assert len(calls) == 1 and result["replayed"] and result["status"] == "unverified"
    row, _ = operations.begin(1, "message:2", "write", {})
    ctx.extras["request_key"] = "message:2"
    result = json.loads(asyncio.run(operations.execute(reg.get("write"), tc, ctx)))
    assert result["status"] == "outcome_unknown" and len(calls) == 1
    assert operations.read(2, row["id"]) is None


class App:
    def __init__(self, reg):
        self._adapters = {}
        self.reg = reg

    def merged_registry(self):
        return self.reg


def setup_job(monkeypatch, handler=None):
    from shared.agent_runtime import config as cfg

    values = cfg.config().copy()
    values["background_tools"] = ["probe"]
    monkeypatch.setattr(followups, "config", lambda: values)

    @tool(read_only=True)
    async def probe(ctx):
        return json.dumps({"ready": True})

    reg = ToolRegistry()
    reg.register(handler or probe)
    ctx = AgentContext(1, "general", "wait until ready", "")
    job = followups.create(
        ctx, reg, "watch", "probe", {}, "json_equals", '{"ready":true}', "2020-01-01T00:00:00Z", "2099-01-01T00:00:00Z"
    )
    return reg, ctx, job


def test_followup_persists_checks_and_notifies_once(monkeypatch):
    reg, _ctx, job = setup_job(monkeypatch)
    sent = []

    async def notify(r):
        sent.append(r["id"])

    asyncio.run(followups.tick(App(reg), notify))
    asyncio.run(followups.tick(App(reg), notify))
    assert sent == [job["id"]]
    row = followups.list_jobs(1)[0]
    assert row["status"] == "completed" and row["notify_state"] == "sent"
    assert not followups.update(2, job["id"], "cancel")


def test_followup_revoked_tool_cannot_run(monkeypatch):
    reg, _ctx, job = setup_job(monkeypatch)
    reg.get("probe").read_only = False

    async def notify(r):
        raise AssertionError("no notification on first probe failure")

    asyncio.run(followups.tick(App(reg), notify))
    row = followups.list_jobs(1)[0]
    assert row["failures"] == 1 and row["status"] == "waiting"


def test_cancel_wins_over_inflight_check(monkeypatch):
    holder = {}

    @tool(read_only=True, name="probe")
    async def probe(ctx):
        followups.update(ctx.user_id, holder["id"], "cancel")
        return '{"ready":true}'

    reg, _ctx, job = setup_job(monkeypatch, probe)
    holder.update(job)

    async def notify(r):
        raise AssertionError("cancelled job must not notify")

    asyncio.run(followups.tick(App(reg), notify))
    assert followups.list_jobs(1)[0]["status"] == "cancelled"


def test_legacy_insight_preserves_evidence_and_revision():
    from shared.memory.insights import get_store

    store = get_store()
    store.record_candidates(1, "global", ["Old preference"], evidence="message:123")
    pending = store.list_pending(1)[0]
    assert store.confirm(pending["id"])
    assert not store.confirm(pending["id"])
    row = store.read_confirmed_records(1, "global")[0]
    assert row["evidence"] == "message:123"
    new = store.revise(1, row["id"], "New preference", "message:124")
    rows = store.read_confirmed_records(1, "global")
    assert len(rows) == 1 and rows[0]["id"] == new
    with pytest.raises(ValueError):
        store.revise(2, new, "No", "forged")


def test_unknown_mutation_forces_honest_final_answer():
    @tool(mutating=True)
    async def write(ctx):
        raise TimeoutError("private details")

    reg = ToolRegistry()
    reg.register(write)
    ctx = AgentContext(1, "general", "do it", "")
    value = json.loads(asyncio.run(operations.execute(reg.get("write"), ToolCall("a", "write", {}), ctx)))
    assert value["status"] == "outcome_unknown"
    assert "private details" not in json.dumps(value)
    assert operations.guard_answer(ctx, "Done successfully") != "Done successfully"
    assert value["operation_id"] in operations.guard_answer(ctx, "Done")


def test_followup_recovers_lease_and_records_delivery_uncertainty(monkeypatch):
    reg, _ctx, job = setup_job(monkeypatch)
    with connection() as db:
        db.execute("UPDATE agent_followups SET status='running',lease_until='2020-01-01' WHERE id=?", (job["id"],))
    calls = []

    async def notify(row):
        calls.append(row["id"])
        raise TimeoutError()

    asyncio.run(followups.tick(App(reg), notify))
    asyncio.run(followups.tick(App(reg), notify))
    assert calls == [job["id"]]
    assert followups.list_jobs(1)[0]["notify_state"] == "delivery_unknown"


def test_followup_expiry_does_not_call_tool(monkeypatch):
    reg, _ctx, job = setup_job(monkeypatch)
    with connection() as db:
        db.execute("UPDATE agent_followups SET expires_at='2020-01-01' WHERE id=?", (job["id"],))

    async def forbidden(**kwargs):
        raise AssertionError("expired job ran")

    reg.get("probe").handler = forbidden
    sent = []

    async def notify(row):
        sent.append(row)

    asyncio.run(followups.tick(App(reg), notify))
    assert sent[0]["status"] == "expired" and sent[0]["failures"] == 0


def test_context_preferences_and_project_are_owner_scoped():
    from shared.agent_runtime.context import TaskContextMemory

    memory.project(1, "robot", "A compact summary", ["robot.md"])
    memory.record(1, "preference", "Answer concisely", "user request", "user_stated")
    memory.record(2, "preference", "Other private preference", "private", "user_stated")
    ctx = AgentContext(1, "general", "continue", "")
    text = asyncio.run(TaskContextMemory().read(ctx))
    assert "robot.md" in text and "Answer concisely" in text and "Other private" not in text


def test_architecture_can_be_disabled(monkeypatch):
    from shared.agent_runtime.tools import attach

    monkeypatch.setattr("shared.agent_runtime.config.enabled", lambda: False)
    registry = ToolRegistry()
    attach(registry)
    assert registry.names() == []


def test_followup_arguments_schema_is_object():
    from shared.agent_runtime.tools import create_agent_followup

    assert create_agent_followup._agent_tool_meta["parameters"]["properties"]["arguments"]["type"] == "object"


@pytest.mark.parametrize(
    "state,expected",
    [("queued", "pending"), ("processing", "pending"), ("created", "verified"), ("outcome_unknown", "outcome_unknown")],
)
def test_calendar_receipt_requires_readback(monkeypatch, state, expected):
    from unified_bot.integrations.verifiers import calendar

    monkeypatch.setattr(
        "planning_bot.services.calendar_bridge.status", lambda owner, rid: {"status": state, "event_id": "event-1"}
    )
    assert asyncio.run(calendar(AgentContext(1, "planning", "", ""), {}, '{"request_id":"req-1"}')) == expected


def test_real_kanban_tool_receipt_reads_back_and_deduplicates(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from planning_bot.app.task_tools import apply_kanban_task
    from planning_bot.services import kanban_agent as ka
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.core.config import BACKLOG_COLUMN, BLOCKED_COLUMN
    monkeypatch.setenv('AGENT_ROOT',str(tmp_path))
    monkeypatch.setenv('KANBAN_AGENT_WRITES','1')
    monkeypatch.setattr(ka,'_sync_state_file',lambda board:None)
    path=tmp_path/'board.md'
    path.write_text(f'---\nkanban-plugin: board\n---\n\n## {BACKLOG_COLUMN}\n\n- [ ] Repair laptop\n\t🆔 ID: aabbccdd\n\n## {BLOCKED_COLUMN}\n')
    board=KanbanBoard(path);board.state_file=tmp_path/'state.json'
    ctx=AgentContext(1,'planning','move task','',extras={'bot':SimpleNamespace(kanban=board,logger=None),'request_key':'message:10'})
    reg=ToolRegistry();reg.register(apply_kanban_task)
    tc=ToolCall('a','apply_kanban_task',{'action':'move','task_id':'aabbccdd','column':BLOCKED_COLUMN})
    result=json.loads(asyncio.run(operations.execute(reg.get(tc.name),tc,ctx)))
    assert result['status']=='verified'
    before=path.read_text()
    result=json.loads(asyncio.run(operations.execute(reg.get(tc.name),tc,ctx)))
    assert result['replayed'] and result['status']=='verified' and path.read_text()==before
