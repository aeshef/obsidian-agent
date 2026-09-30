import json
from datetime import datetime, timezone
from types import SimpleNamespace
from unified_bot.integrations import dashboard_datasets as datasets
from shared.obsidian_ui import layout, freshness


def test_existing_dashboard_refreshes_dataset_without_changing_markdown(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(layout,'install_assets',lambda v:'ui')
    monkeypatch.setattr(datasets,'export_dataset',lambda v,r,k:calls.append(k))
    body='---\nassistant-ui: true\n---\nUser layout'
    assert layout.present_dashboard(body,tmp_path,'progress')==body
    assert calls==['progress']


def test_progress_refresh_independent_of_page_and_png(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr('shared.capabilities.sync_steps.sync_step_enabled',lambda s:True)
    monkeypatch.setattr(datasets,'export_dataset',lambda v,r,k:calls.append(k))
    datasets.refresh_progress(tmp_path)
    assert calls==['progress']
    monkeypatch.setattr('shared.capabilities.sync_steps.sync_step_enabled',lambda s:False)
    datasets.refresh_progress(tmp_path)
    assert calls==['progress']


def test_stale_dataset_not_masked_by_recent_file_mtime(tmp_path,monkeypatch):
    monkeypatch.setattr(freshness,'get_capabilities',lambda:SimpleNamespace(module=lambda n:n=='planning',connector=lambda n:False))
    monkeypatch.setattr(freshness,'folder',lambda n:'dash')
    monkeypatch.setattr(freshness,'dashboards_sub',lambda n:'data')
    monkeypatch.setattr(freshness,'ui_config',lambda:{'layout':{'view_root':'ui'},'freshness':{'max_age_seconds':7200,'daily_seconds':93600}})
    p=tmp_path/'dash/data/ui';p.mkdir(parents=True)
    (p/'progress.json').write_text(json.dumps({'generated_at':'2026-09-23T00:00:00Z'}))
    statuses=freshness.dataset_status(tmp_path,datetime(2026,9,28,tzinfo=timezone.utc))
    assert statuses['progress']['status']=='stale'
    assert statuses['analytics']['status']=='missing'
