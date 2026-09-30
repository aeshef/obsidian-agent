from pathlib import Path
import json

def test_calendar_splits_midnight_and_excludes_all_day(tmp_path, monkeypatch):
    from unified_bot.integrations import dashboard_datasets as d
    monkeypatch.setattr(d,'folder',lambda _: 'dash')
    monkeypatch.setattr(d,'dashboards_sub',lambda _: 'data')
    monkeypatch.setattr(d,'vault_file',lambda _: 'calendar.json')
    p=tmp_path/'dash/data';p.mkdir(parents=True)
    event={'date':'2026-09-01','start':'23:00','end_date':'2026-09-02','end':'01:00','title':'Event','calendar':'Calendar'}
    (p/'calendar.json').write_text(json.dumps({'events':[event,dict(event,is_allday=True),dict(event,is_cancelled=True)]}))
    out=d.build_dataset(tmp_path,'calendar')['charts'][0]['rows']
    assert [(x['date'],x['value']) for x in out]==[('2026-09-01',1),('2026-09-02',1)]

def test_missing_source_does_not_invent_observations(tmp_path):
    from unified_bot.integrations.dashboard_datasets import build_dataset
    result=build_dataset(tmp_path,'calendar')
    assert result['charts'][0]['rows']==[]
