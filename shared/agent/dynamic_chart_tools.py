"""Discover and render parameterized dashboard charts for the assistant."""
import asyncio
import json
from datetime import date,timedelta
from shared.agent.tools import tool
from shared.agent.types import AgentContext
from shared.paths import vault_root_optional
from shared.obsidian_ui.config import ui_config


@tool(category='charts')
async def list_dashboard_charts(ctx: AgentContext, dashboard: str='progress') -> str:
    """Discover dynamic chart IDs, semantics and supported filters for progress/health/calendar/analytics/finance/system/maintenance. Prefer these charts to legacy PNG lookup. Call before render_dashboard_chart."""
    from shared.obsidian_ui.chart_export import chart_dataset
    vault=vault_root_optional()
    if vault is None:return json.dumps({'error':'vault_unavailable'})
    try:data=await asyncio.to_thread(chart_dataset,vault,dashboard)
    except (ValueError,OSError) as e:return json.dumps({'error':str(e)})
    return json.dumps({'dashboard':dashboard,'charts':[{k:v for k,v in s.items() if k!='rows'}|{'rows':len(s['rows'])} for s in data.get('charts',[])]},ensure_ascii=False)


@tool(category='charts')
async def render_dashboard_chart(ctx: AgentContext, dashboard: str, chart_id: str, start: str='', end: str='', grain: str='auto', filters_json: str='{}', x_metric: str='', y_metric: str='', lag: int=0) -> str:
    """Build and send ONE requested chart using dashboard data. Use list_dashboard_charts IDs. ISO start/end; grain day/week/month/quarter/auto; filters_json object with category/account/goal/priority. For relationship charts choose x_metric/y_metric from metrics and lag 0/1/2/3/7. Current snapshots ignore dates and say so. No arbitrary code, paths or SQL. Call only when the user requests a chart/image."""
    from shared.obsidian_ui.chart_export import export_chart
    from shared.agent.chart_tools import _deliver_charts_now
    from shared.agent.media_queue import queue_chart_media
    vault=vault_root_optional()
    if vault is None:return json.dumps({'error':'vault_unavailable'})
    try:
        filters=json.loads(filters_json)
        if not isinstance(filters,dict) or any(k not in ('category','account','goal','priority') or not isinstance(v,str) for k,v in filters.items()):raise ValueError('invalid_filters')
        end=end or date.today().isoformat()
        start=start or (date.fromisoformat(end)-timedelta(days=ui_config()['interactive']['default_days']-1)).isoformat()
        path,meta=await asyncio.to_thread(export_chart,vault,dashboard,chart_id,start,end,grain,filters,x_metric,y_metric,lag)
    except (ValueError,OSError) as e:return json.dumps({'error':str(e)})
    items=[(str(path.relative_to(vault)),meta['title']+' · '+meta['period'])]
    delivered=await _deliver_charts_now(ctx,items)
    if not delivered:queue_chart_media(ctx,items,max_total=1)
    return json.dumps({'status':'sent' if delivered else 'queued',**meta},ensure_ascii=False)
