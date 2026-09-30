"""Publish trace aggregates without prompts, responses or account identifiers."""
import json
from datetime import datetime
from shared.obsidian_ui.assets import install_assets
from shared.obsidian_ui.config import ui_config
from shared.obsidian_ui.series import series_chart


def export_system(vault, daily, traces):
    from shared.agent.trace_analytics import parse_ts, _local_day
    cfg=ui_config();L=cfg['labels'];dates=[r['date'] for r in daily]
    charts=[series_chart(cid,L[cid],dates,{L[cid]:[r[key] for r in daily]},method='sum')
            for cid,key in [('agent_tokens','tokens'),('agent_cost','est_cost_usd')]]
    tools=[]
    for r in traces:
        day=_local_day(parse_ts(r.get('ts')))
        if day=='unknown':continue
        for it in r.get('tool_iters') or []:
            for name in it.get('tools') or []:
                tools.append(dict(date=day,series=str(name),value=1))
    charts.append(dict(id='agent_tools',title=L['agent_tools'],type='bar',method='sum',rows=tools,max_series=cfg['interactive']['max_series']))
    root=install_assets(vault);dest=vault/root/'system.json';temp=dest.with_suffix('.tmp')
    temp.write_text(json.dumps(dict(generated_at=datetime.now().astimezone().isoformat(),charts=charts),ensure_ascii=False));temp.replace(dest)
