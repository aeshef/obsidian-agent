import json
from datetime import datetime, timezone
import pytest
from planning_bot.services import calendar_bridge as bridge
from planning_bot.services.calendar_snapshot import reconcile


@pytest.fixture
def cfg(monkeypatch):
    c = dict(bridge.config(), enabled=True, write_enabled=True)
    monkeypatch.setattr(bridge, "config", lambda: c)
    return c


def payload():
    return bridge.normalize('Focus', '2026-09-20T10:00:00+03:00', '2026-09-20T11:00:00+03:00')


def test_queue_idempotent_and_owner_isolation(tmp_path, cfg):
    p = tmp_path/'queue.db'
    a = bridge.enqueue(1, payload(), p)
    assert bridge.enqueue(1, payload(), p) == a
    assert bridge.status(2, a['request_id'], p)['status'] == 'not_found'
    claim = bridge.rpc({'action':'claim'}, p)['request']
    assert claim['allow_create'] is True
    assert bridge.rpc({'action':'claim'}, p)['request'] is None
    assert not bridge.rpc({'action':'ack', 'request_id':claim['request_id'], 'lease':'wrong', 'result':{'status':'created','event_id':'e'}}, p)['acknowledged']
    assert bridge.rpc({'action':'ack', 'request_id':claim['request_id'], 'lease':claim['lease'], 'result':{'status':'created','event_id':'e'}}, p)['acknowledged']
    assert bridge.enqueue(1,payload(),p)['created_in_calendar'] is True


def test_lost_native_result_is_never_replayed_as_create(tmp_path, cfg):
    p=tmp_path/'q.db'; bridge.enqueue(1,payload(),p)
    bridge.rpc({'action':'claim'},p)
    with bridge.connection(p) as db: db.execute('UPDATE requests SET lease_until=0')
    second=bridge.rpc({'action':'claim'},p)['request']
    assert second['allow_create'] is False


@pytest.mark.parametrize('start,end', [('2026-01-01T10:00','2026-01-01T11:00'),('2026-01-01T12:00+03:00','2026-01-01T11:00+03:00')])
def test_reject_ambiguous_time_and_negative_duration(cfg,start,end):
    with pytest.raises(ValueError): bridge.normalize('Focus',start,end)


def snapshot(events):
    return dict(schema_version=1, complete=True, captured_at='2026-09-13T12:00:00Z',window_start='2026-09-01T00:00:00Z',window_end='2026-10-01T00:00:00Z',calendars=[{'id':'cal'}],events=events)


def event(start='2026-09-15T10:00:00Z',end='2026-09-15T11:00:00Z'):
    return dict(native_id='abc',occurrence_start=start,calendar_id='cal',calendar='Test',start_at=start,end_at=end,title='Focus',is_allday=False,is_cancelled=False)


def test_empty_complete_snapshot_removes_deleted_events():
    d=reconcile({},snapshot([event()]),'Europe/Moscow')
    assert len(d['events'])==1
    assert reconcile(d,snapshot([]),'Europe/Moscow')['events']==[]


def test_reschedule_replaces_occurrence_and_preserves_other_calendar():
    d=reconcile({},snapshot([event()]),'Europe/Moscow')
    moved=event('2026-09-16T10:00:00Z','2026-09-16T11:00:00Z')
    d=reconcile(d,snapshot([moved]),'Europe/Moscow')
    assert len(d['events'])==1 and d['events'][0]['date']=='2026-09-16'


def test_refuse_partial_and_out_of_order_snapshot():
    s=snapshot([]);s['complete']=False
    with pytest.raises(ValueError):reconcile({},s,'UTC')
    s=snapshot([])
    with pytest.raises(ValueError):reconcile({'meta':{'source_captured_at':'2026-09-14T00:00:00Z'}},s,'UTC')


def test_archive_is_not_counted_twice():
    d={'events':[{'id':'old','date':'2026-08-01','start':'10:00','end':'11:00','title':'old'}]}
    d=reconcile(d,snapshot([]),'UTC')
    assert d['archive']['monthly'][0]['meeting_minutes']==60
    d=reconcile(d,snapshot([]),'UTC')
    assert d['archive']['monthly'][0]['meeting_minutes']==60


def test_missing_source_is_degraded_even_after_successful_transport():
    from scripts.check_pipeline_freshness import source_status
    now=datetime(2026,9,13,tzinfo=timezone.utc)
    assert source_status('2026-08-30T20:00:00Z',93600,now)['status']=='stale'
    assert source_status(None,93600,now)['status']=='missing'


def test_native_duration_and_midnight_visibility():
    from planning_bot.services.calendar_retention import _event_minutes
    from planning_bot.services.calendar_service import _in_range
    from datetime import date
    e=reconcile({},snapshot([event('2026-09-15T20:30:00Z','2026-09-15T22:30:00Z')]),'Europe/Moscow')['events'][0]
    assert _event_minutes(e)==120
    assert _in_range(e,date(2026,9,16),date(2026,9,16))


def test_existing_legacy_archive_month_is_not_recounted():
    d={'archive':{'monthly':[{'month':'2026-08','meeting_count':1,'meeting_minutes':60,'meeting_hours':1}]},
       'events':[{'id':'old','date':'2026-08-01','start':'10:00','end':'11:00','title':'old'}]}
    d=reconcile(d,snapshot([]),'UTC')
    assert d['archive']['monthly'][0]['meeting_minutes']==60


def test_calendar_freshness_message_exists(tmp_path):
    from planning_bot.services.calendar_freshness import describe_calendar
    assert describe_calendar(tmp_path/'missing.json')


def test_launchservices_exit_does_not_hide_committed_native_result(monkeypatch):
    from scripts import calendar_bridge_worker as worker
    from pathlib import Path
    from types import SimpleNamespace
    def run(args, **kwargs):
        Path(args[args.index('--output')+1]).write_text(json.dumps({'status':'created','event_id':'verified'}))
        return SimpleNamespace(returncode=1)
    monkeypatch.setattr(worker.subprocess,'run',run)
    assert worker.native({'action':'create'})=={'status':'created','event_id':'verified'}


def test_no_native_receipt_is_uncertain_not_failed(monkeypatch):
    from scripts import calendar_bridge_worker as worker
    from types import SimpleNamespace
    monkeypatch.setattr(worker.subprocess,'run',lambda *a,**kw:SimpleNamespace(returncode=1))
    assert worker.native({'action':'create'})['status']=='outcome_unknown'
