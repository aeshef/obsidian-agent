from __future__ import annotations

from datetime import datetime, timedelta, timezone


def test_parse_synth_patterns_accepts_kind_objects():
    from shared.memory.insight_format import KIND_DURABLE, KIND_PERIODIC, parse_synth_patterns

    out = parse_synth_patterns(
        {
            "patterns": [
                {"text": "prefers short answers", "kind": "durable"},
                {"text": "food spend up this month", "kind": "periodic"},
                "legacy string",
            ]
        }
    )
    assert out == [
        ("prefers short answers", KIND_DURABLE),
        ("food spend up this month", KIND_PERIODIC),
        ("legacy string", KIND_DURABLE),
    ]


def test_periodic_confirmed_expires_after_ttl(tmp_path, monkeypatch):
    from shared.memory.insights import InsightsStore

    monkeypatch.setenv("INSIGHTS_PERIODIC_TTL_DAYS", "7")
    from shared.memory import config as mem_cfg

    mem_cfg.load_memory_config.cache_clear()

    store = InsightsStore(tmp_path / "memory.db")
    store.record_candidates(1, "finance", [("monthly spike", "periodic")])
    pending = store.list_pending(1, "finance")[0]
    assert store.confirm(pending["id"])

    old = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat(timespec="seconds")
    with store._conn() as conn:
        conn.execute(
            "UPDATE insights SET confirmed_at=? WHERE user_id=? AND domain=?",
            (old, 1, "finance"),
        )
        conn.commit()

    assert store.read_confirmed(1, "finance") == []
    assert store.prune_expired() >= 0


def test_confirm_preserves_kind(tmp_path):
    from shared.memory.insights import InsightsStore

    store = InsightsStore(tmp_path / "memory.db")
    store.record_candidates(1, "planning", [("night closes", "durable")])
    pid = store.list_pending(1, "planning")[0]["id"]
    assert store.confirm(pid)
    rows = store.read_confirmed_records(1, "planning")
    assert rows[0]["pattern_text"] == "night closes"
    assert rows[0]["kind"] == "durable"


def test_format_confirmed_for_prompt_includes_date(tmp_path):
    from shared.memory.insights import InsightsStore

    store = InsightsStore(tmp_path / "memory.db")
    store.record_candidates(1, "finance", [("pattern", "durable")])
    pid = store.list_pending(1, "finance")[0]["id"]
    assert store.confirm(pid)
    lines = store.format_confirmed_for_prompt(1, "finance", limit=1)
    assert lines and lines[0].startswith("- [")
