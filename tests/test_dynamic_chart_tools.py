import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from shared.agent import dynamic_chart_tools as tools
from shared.agent.types import CHART_MEDIA_EXTRAS_KEY


def test_discovery_and_sending_are_registered():
    from shared.agent.tools import ToolRegistry
    from shared.agent.chart_tools import attach_chart_tools
    registry=ToolRegistry();attach_chart_tools(registry)
    assert 'render_dashboard_chart' in registry._tools
    assert 'list_dashboard_charts' in registry._tools


def test_export_is_queued_when_telegram_not_present(monkeypatch,tmp_path):
    import shared.obsidian_ui.chart_export as exporter
    monkeypatch.setattr(tools,'vault_root_optional',lambda:tmp_path)
    p=tmp_path/'.sync/chart_exports/test.png';p.parent.mkdir(parents=True);p.write_bytes(b'fake')
    monkeypatch.setattr(exporter,'export_chart',lambda *a:(p,dict(title='WIP',period='2026-09-01 → 2026-09-02',rows=2)))
    ctx=SimpleNamespace(extras={})
    result=json.loads(asyncio.run(tools.render_dashboard_chart(ctx,'progress','wip_segments','2026-09-01','2026-09-02')))
    assert result['status']=='queued'
    assert ctx.extras[CHART_MEDIA_EXTRAS_KEY][0][0]=='.sync/chart_exports/test.png'


def test_invalid_filter_cannot_reach_renderer(monkeypatch,tmp_path):
    monkeypatch.setattr(tools,'vault_root_optional',lambda:tmp_path)
    ctx=SimpleNamespace(extras={})
    result=json.loads(asyncio.run(tools.render_dashboard_chart(ctx,'progress','x',filters_json='{"path":"/etc/passwd"}')))
    assert result['error']=='invalid_filters' and not ctx.extras
