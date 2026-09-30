import sqlite3
from datetime import datetime, timedelta
import json


def test_replica_includes_committed_wal_and_is_atomic(tmp_path):
    from finance_bot.bot.finance_db_paths import mirror_canonical_to_vault_replica
    src, dst = tmp_path/'source.db', tmp_path/'replica.db'
    con = sqlite3.connect(src)
    con.execute('PRAGMA journal_mode=WAL')
    con.execute('CREATE TABLE transactions(id INTEGER PRIMARY KEY)')
    con.execute('INSERT INTO transactions VALUES(1)')
    con.commit()
    assert mirror_canonical_to_vault_replica(canonical=src, replica=dst)
    with sqlite3.connect(dst) as replica:
        assert replica.execute('PRAGMA quick_check').fetchone() == ('ok',)
        assert replica.execute('SELECT count(*) FROM transactions').fetchone() == (1,)
    previous = dst.read_bytes()
    bad = tmp_path/'bad.db'; bad.write_text('invalid sqlite')
    assert not mirror_canonical_to_vault_replica(canonical=bad, replica=dst)
    assert dst.read_bytes() == previous
    con.close()


def test_dense_cache_can_reload_without_embedding(tmp_path):
    import numpy as np
    from knowledge_bot.services.query.dense_index import DenseIndex, _save_cache, _load_cache
    path = tmp_path/'dense.npz'
    original = DenseIndex(['a.md'], ['hash'], np.array([[1., 0.]], dtype=np.float32), model='test')
    _save_cache(original, path)
    restored = _load_cache(path, model='test')
    assert restored.paths == ['a.md']
    np.testing.assert_array_equal(restored.matrix, original.matrix)
    assert list(tmp_path.iterdir()) == [path]


def test_monitor_uses_marker_content_and_current_failures(tmp_path):
    from shared.analytics.pipeline_status import _age_hours, _pipeline_problems
    ok = tmp_path/'last_sync_ok.txt'
    ok.write_text((datetime.now()-timedelta(days=2)).isoformat())
    assert _age_hours(ok) > 47
    (tmp_path/'last_sync_failed.txt').write_text(datetime.now().isoformat()+' step=import')
    (tmp_path/'pipeline_health.json').write_text(json.dumps({'checked_at': datetime.now().isoformat(), 'status':'degraded', 'sources':{'iphone':{'status':'stale'}}}))
    problems = _pipeline_problems(tmp_path)
    assert any('step=import' in p for p in problems)
    assert 'iphone: stale' in problems


def test_health_queue_ack_requires_valid_packet_and_replays_safely(tmp_path):
    import hashlib
    from scripts.health_queue_rpc import accept_packets
    body = 'ts: 2026-09-18T00:00:00+03:00\nschema_version: 2\nmeasurement_day: 2026-09-18\ncaptured_at: 2026-09-19T12:00:00+03:00\nmetric_group: activity\nread_status: ok\nsteps: 2500\n'
    packet = {'body':body, 'sha256':hashlib.sha256(body.encode()).hexdigest()}
    result = accept_packets([packet], tmp_path)
    assert result == {'accepted':[packet['sha256']], 'rejected':[]}
    assert accept_packets([packet], tmp_path) == result
    assert len(list(tmp_path.glob('*.txt'))) == 1
    invalid = {'body':'', 'sha256':hashlib.sha256(b'').hexdigest()}
    assert accept_packets([invalid], tmp_path)['accepted'] == []


def test_payment_cooldown_is_scoped_to_credential(tmp_path, monkeypatch):
    from shared import llm_payment_guard as guard
    import requests
    import pytest
    monkeypatch.setattr(guard, '_state', lambda url, key: tmp_path/(key+'.json'))
    guard.record('https://example.invalid', 'test', 402)
    with pytest.raises(requests.HTTPError) as error:
        guard.check('https://example.invalid', 'test')
    assert error.value.response.status_code == 402
    guard.check('https://example.invalid', 'different')


def test_orphan_archive_preserves_history_and_is_idempotent():
    from finance_bot.bot.services.balance_history_integrity import archive_orphaned_snapshots
    db=sqlite3.connect(':memory:')
    db.executescript('CREATE TABLE accounts(id INTEGER PRIMARY KEY); CREATE TABLE account_balance_snapshots(id INTEGER PRIMARY KEY,account_id INTEGER REFERENCES accounts(id),snapshot_date DATE,balance NUMERIC); INSERT INTO accounts VALUES(1); INSERT INTO account_balance_snapshots VALUES(1,1,"2026-01-01",10.25),(2,2,"2026-01-02",20.75);')
    assert archive_orphaned_snapshots(db)==1
    assert db.execute('PRAGMA foreign_key_check').fetchall()==[]
    assert db.execute('SELECT original_id,account_id,snapshot_date,balance FROM archived_account_balance_snapshots').fetchone()==(2,2,'2026-01-02',20.75)
    assert archive_orphaned_snapshots(db)==0
    assert db.execute('SELECT count(*) FROM account_balance_snapshots').fetchone()==(1,)


def test_sleep_debt_today_does_not_present_frozen_history_as_current():
    from shared.analytics.sleep_debt import sleep_debt_today
    assert sleep_debt_today([{'debt':5,'missing':False},{'debt':5,'missing':True}]) is None


def test_finance_connections_enforce_foreign_keys(monkeypatch):
    import asyncio
    from types import SimpleNamespace
    from finance_bot.bot import db
    from sqlalchemy import text
    monkeypatch.setattr(db, 'get_settings', lambda: SimpleNamespace(DATABASE_URL='sqlite+aiosqlite:///:memory:'))
    async def check():
        engine=db.get_engine()
        async with engine.connect() as con:
            assert (await con.execute(text('PRAGMA foreign_keys'))).scalar()==1
        await engine.dispose()
    asyncio.run(check())


def test_health_history_survives_rsync_delete(tmp_path):
    import subprocess
    src,dst=tmp_path/'source',tmp_path/'target'
    (src/'Data/Actions/IPhone').mkdir(parents=True)
    (dst/'Data/Actions/IPhone').mkdir(parents=True)
    (dst/'Data/Actions/IPhone/server-only.txt').write_text('revision')
    (dst/'obsolete.txt').write_text('obsolete')
    subprocess.run(['rsync','-a','--delete','--filter=P Data/Actions/IPhone/***',str(src)+'/',str(dst)+'/'],check=True)
    assert (dst/'Data/Actions/IPhone/server-only.txt').read_text()=='revision'
    assert not (dst/'obsolete.txt').exists()


def test_local_mac_retention_preserves_unmaterialized_and_undelivered(tmp_path):
    from planning_bot.services.mac_capture import connection, maintain
    db=connection(tmp_path/'capture.db')
    db.execute("INSERT INTO events(id,ts,body,ack,materialized) VALUES('done',1,'{}',0,1),('pending',1,'{}',0,0)")
    db.commit()
    cfg={'raw_days':90,'aggregate_days':730}
    maintain(db,tmp_path,cfg)
    assert db.execute('SELECT count(*) FROM events').fetchone()[0]==2
    maintain(db,tmp_path,cfg,local_only=True)
    assert [r[0] for r in db.execute('SELECT id FROM events')]==['pending']
