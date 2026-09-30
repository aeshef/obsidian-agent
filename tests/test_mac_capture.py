import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from planning_bot.services.mac_capture import aggregate, connection, ingest, materialize, report
from scripts.mac_capture_worker import deliver, drain

CFG = {"batch_size": 1000, "idle_seconds": 120, "max_interval_seconds": 90, "stale_seconds": 180}


def event(ts, *, sid="00000000-0000-0000-0000-000000000001", kind="heartbeat", idle=0, awake=True):
    return dict(id=str(uuid.uuid4()), session_id=sid, ts=ts.isoformat(), kind=kind,
                idle_sec=idle, app="Editor", bundle_id="test.editor", awake=awake, session_active=True)


def test_replayed_outbox_is_idempotent(tmp_path):
    spool = tmp_path/"outbox"; spool.mkdir()
    row = event(datetime.now(timezone.utc))
    db = connection(tmp_path/"events.db")
    for _ in range(2):
        (spool/"one.json").write_text(json.dumps(row))
        assert drain(db, spool) == []
    assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    assert not list(spool.iterdir())


def test_lost_ack_retries_same_ids(tmp_path):
    db = connection(tmp_path/"events.db")
    row = event(datetime.now(timezone.utc))
    ingest(db, [row])
    received = []
    def fail(rows, cfg):
        received.extend(r["id"] for r in rows)
        raise TimeoutError()
    with pytest.raises(TimeoutError):
        deliver(db, CFG, fail)
    assert report(db, CFG)["pending_events"] == 1
    assert deliver(db, CFG, lambda rows, cfg: {"accepted": [r["id"] for r in rows]}) == 1
    assert received == [row["id"]]
    assert report(db, CFG)["pending_events"] == 0


def test_invalid_ack_never_clears_queue(tmp_path):
    db = connection(tmp_path/"events.db")
    ingest(db, [event(datetime.now(timezone.utc))])
    with pytest.raises(ValueError):
        deliver(db, CFG, lambda rows, cfg: {"accepted": [str(uuid.uuid4())]})
    assert report(db, CFG)["pending_events"] == 1


def test_partial_capture_is_retained(tmp_path):
    spool = tmp_path/"outbox"; spool.mkdir()
    (spool/"broken.json").write_text('{')
    assert drain(connection(tmp_path/"db"), spool) == ["JSONDecodeError"]
    assert (spool/"broken.json").exists()


def test_gaps_restarts_idle_and_hours(tmp_path):
    db = connection(tmp_path/"db")
    t = datetime(2026, 9, 1, 10, 59, 30, tzinfo=timezone.utc)
    rows = [event(t), event(t+timedelta(seconds=60), idle=300),
            event(t+timedelta(seconds=120)), event(t+timedelta(hours=3))]
    ingest(db, rows)
    aggregate(db, CFG)
    hours = [json.loads(r[0]) for r in db.execute("SELECT body FROM hours")]
    totals = {k:sum(h["states"].get(k,0) for h in hours) for k in ("active","idle","unknown")}
    assert totals == {"active":60, "idle":60, "unknown":10680}
    # Rebuilding cannot double-count.
    aggregate(db, CFG)
    assert [json.loads(r[0]) for r in db.execute("SELECT body FROM hours")] == hours


def test_session_restart_is_unknown(tmp_path):
    db = connection(tmp_path/"db")
    t = datetime.now(timezone.utc)-timedelta(minutes=2)
    ingest(db, [event(t), event(t+timedelta(seconds=60), sid=str(uuid.uuid4()))])
    aggregate(db, CFG)
    assert sum(json.loads(r[0])["states"].get("unknown",0) for r in db.execute("SELECT body FROM hours")) == 60


def test_materialized_legacy_parser_preserves_state(tmp_path, monkeypatch):
    from planning_bot.services.context_parser import parse_context_file
    monkeypatch.setenv("TIMEZONE", "UTC")
    db = connection(tmp_path/"db")
    row = event(datetime(2026,9,1,10,0,tzinfo=timezone.utc), awake=False, idle=0.2)
    ingest(db,[row]); materialize(db,tmp_path/"vault",{"2026-09-01"},CFG)
    path = tmp_path/"vault/2026-09-01, 00-00_9001.txt"
    snap = parse_context_file(path)[0]
    assert snap["active"] is False
    assert snap["idle_sec"] == 0
    assert snap["bundle_id"] == "test.editor"


def test_conflict_rolls_back_entire_batch(tmp_path):
    db = connection(tmp_path/"db")
    row=event(datetime.now(timezone.utc)); ingest(db,[row])
    other=event(datetime.now(timezone.utc))
    with pytest.raises(ValueError):
        ingest(db,[other,{**row,"app":"different"}])
    assert db.execute("SELECT count(*) FROM events").fetchone()[0] == 1
