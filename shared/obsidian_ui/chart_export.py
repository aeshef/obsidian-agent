"""Render a requested chart to a short-lived PNG, never a scheduled vault report."""
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4
from threading import RLock
_RENDER_LOCK=RLock()
import json
from shared.obsidian_ui.config import ui_config
from shared.obsidian_ui.chart_query import query_chart
from shared.vault_paths_config import folder, dashboards_sub


def chart_dataset(vault, kind):
    from shared.capabilities.profile import get_capabilities
    profile=get_capabilities()
    if kind not in ('progress','health','calendar','analytics','finance','system','maintenance'):raise ValueError('unknown_dashboard')
    enabled=profile.any_module('finance','planning','knowledge') if kind=='system' else profile.module('finance' if kind=='finance' else 'knowledge' if kind=='maintenance' else 'planning')
    if not enabled:raise ValueError('module_disabled')
    root=vault/folder('dashboards')/dashboards_sub('data')/ui_config()['layout']['view_root']
    if kind=='finance':
        data=json.loads((root/'finance.json').read_text())
    else:
        from unified_bot.integrations.dashboard_datasets import build_dataset
        data=build_dataset(vault,kind)
    return data


def _export_chart(vault: Path, kind: str, chart_id: str, start: str, end: str, grain='auto', filters=None, x_metric='', y_metric='', lag=0):
    data=chart_dataset(vault,kind);cfg=ui_config();L=cfg['labels']
    spec=next((s for s in data.get('charts',[]) if s['id']==chart_id),None)
    if not spec:raise ValueError('unknown_chart_id')
    spec=dict(spec,x_metric=x_metric,y_metric=y_metric,lag=lag)
    result=query_chart(spec,start,end,grain,filters or {},cfg['interactive']['max_range_days'])
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import numpy as np
    width=cfg['interactive']['export_width'];height=cfg['interactive']['export_height']
    fig,ax=plt.subplots(figsize=(width/100,height/100),dpi=100)
    xs=result['x'];x=np.arange(len(xs));palette=cfg['chart']['series_palette']
    if spec['type']=='scatter':
        points=result['points']
        if points:ax.scatter([p[0] for p in points],[p[1] for p in points],s=20)
        ax.set_xlabel(L.get(result['x_metric'],result['x_metric']));ax.set_ylabel(L.get(result['y_metric'],result['y_metric']))
    elif spec['type'] in ('heatmap','correlation'):
        matrix=np.array([s['values'] for s in result['series']],dtype=float)
        im=ax.imshow(matrix,aspect='auto',cmap='coolwarm' if spec['type']=='correlation' else 'Blues', **({'vmin':-1,'vmax':1} if spec['type']=='correlation' else {}));fig.colorbar(im,ax=ax)
        ax.set_yticks(range(len(result['series'])),[L.get(s['name'],s['name']) for s in result['series']])
    else:
        bottom=np.zeros(len(xs));stack=spec.get('stack',spec['type'] in ('bar','categorical'))
        for i,s in enumerate(result['series']):
            values=np.array([np.nan if v is None else v for v in s['values']]);color=palette[i%len(palette)]
            if spec['type'] in ('bar','categorical'):
                if stack:ax.bar(x,values,bottom=bottom,label=s['name'],color=color);bottom+=np.nan_to_num(values)
                else:
                    w=.8/len(result['series']);ax.bar(x+(i-(len(result['series'])-1)/2)*w,values,width=w,label=s['name'],color=color)
            elif spec.get('area'):
                ax.fill_between(x,bottom,bottom+values,label=s['name'],color=color,alpha=.75);bottom+=np.nan_to_num(values)
            else:ax.plot(x,values,label=s['name'],color=color)
        ax.legend(loc='upper left',fontsize=8,ncol=min(3,len(result['series'])))
    if spec['type']!='scatter':
        step=max(1,len(xs)//12);ax.set_xticks(x[::step],[L.get(d,d) for d in xs[::step]],rotation=30,ha='right')
    period=L['snapshot_note']+' · '+spec['snapshot'] if spec.get('snapshot') else start+' → '+end
    ax.set_title(spec['title']+'\n'+period)
    if spec['type']!='scatter':ax.set_ylabel(spec.get('unit',''))
    fig.tight_layout()
    cache=vault/'.sync/chart_exports';cache.mkdir(parents=True,exist_ok=True)
    cutoff=datetime.now().timestamp()-timedelta(hours=cfg['interactive']['export_cache_hours']).total_seconds()
    for p in cache.glob('*.png'):
        if p.stat().st_mtime<cutoff:p.unlink(missing_ok=True)
    target=cache/(uuid4().hex+'.png')
    try:fig.savefig(target)
    finally:plt.close(fig)
    return target,dict(chart=chart_id,title=spec['title'],period=period,source_updated=spec.get('source_updated') or data.get('source_updated') or data.get('generated_at'),**{k:result[k] for k in ('grain','rows')})


def export_chart(*args, **kwargs):
    with _RENDER_LOCK:
        return _export_chart(*args, **kwargs)
