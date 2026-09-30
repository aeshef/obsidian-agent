"""Small read-only chart datasets; no edits to domain records."""
from pathlib import Path
from datetime import datetime, timedelta
import json, math
from shared.vault_paths_config import folder, dashboards_sub, vault_file, vault_rel_path
from shared.chart_paths import chart_path
from shared.obsidian_ui.config import ui_config


def read_json(path):
    return json.loads(path.read_text()) if path.is_file() else {}


def build_dataset(vault: Path, kind: str):
    cfg=ui_config();L=cfg['labels'];data=vault/folder('dashboards')/dashboards_sub('data')
    result={'generated_at':datetime.now().astimezone().isoformat(timespec='minutes'),'charts':[],'filters':[]}
    if kind=='health':
        from planning_bot.services.iphone_context_parser import get_snapshots
        from planning_bot.services.snapshot_query import latest_per_calendar_day
        from shared.analytics.series import sanitize_metric
        days=latest_per_calendar_day(get_snapshots(data/vault_rel_path('actions_iphone'),days=None))
        for snapshot in days.values():
            macros=[snapshot.get(k) for k in ('proteins_g','fats_g','carbs_g')]
            if all(isinstance(v,(int,float)) for v in macros):
                snapshot['kcal_macros']=sum(v*w for v,w in zip(macros,(4,9,4)))
        for metric in cfg['interactive']['metrics']:
            rows=[]
            for day,s in sorted(days.items()):
                from shared.analytics.sleep_parse import parse_sleep_detail
                raw=parse_sleep_detail(s.get('sleep_detail')).get(metric) if metric.startswith('iphone_sleep_') else s.get(metric)
                value=sanitize_metric(metric,raw)
                if math.isfinite(value):rows.append({'date':day.isoformat(),'value':float(value),'series':L.get(metric,metric)})
            result['charts'].append({'id':metric,'title':L.get(metric,metric),'method':'mean','type':'line','rows':rows,'smooth':True})
        from shared.obsidian_ui.series import series_chart
        dates=[d.isoformat() for d in sorted(days)]
        for spec in cfg['interactive']['health_groups']:
            series={L.get(k,k):[parse_sleep_detail(days[d].get('sleep_detail')).get(k) if k.startswith('iphone_sleep_') else days[d].get(k) for d in sorted(days)] for k in spec['metrics']}
            result['charts'].append(series_chart(spec['id'],L[spec['id']],dates,series,chart_type='bar'))
        from shared.obsidian_ui.series import finite
        metrics=cfg['interactive']['metrics']
        observations=[dict(date=d.isoformat(),**{k:finite(parse_sleep_detail(s.get('sleep_detail')).get(k) if k.startswith('iphone_sleep_') else s.get(k)) for k in metrics}) for d,s in sorted(days.items())]
        result['charts'].append(dict(id='health_correlation',title=L['panel_correlation'],type='correlation',method='mean',rows=observations,metrics=metrics,min_pairs=cfg['interactive']['min_correlation_pairs']))
        result['charts'].append(dict(id='health_relationship',title=L['panel_relationship'],type='scatter',method='mean',rows=observations,metrics=metrics,min_pairs=cfg['interactive']['min_correlation_pairs']))
    elif kind=='progress':
        from planning_bot.services.action_log_parser import collect_events_from_logs,is_completion_event
        events=collect_events_from_logs(vault/folder('dashboards')/dashboards_sub('logs'))
        result['filters']=['category','goal','priority']
        mapping=read_json(vault/folder('dashboards')/vault_file('goals_mapping_json'))
        from planning_bot.services.kanban_index import load_kanban_priority_index
        priorities,_,_=load_kanban_priority_index(vault)
        result['note']=L['task_filter_note']
        seen=set();created=[];completed=[]
        for e in events:
            d=e.get('data') or {};tid=d.get('task_id');typ='tasks_completed' if is_completion_event(e) else 'tasks_created' if e.get('type')=='task_created' else None
            if not typ:continue
            # A move to Done and a completion event can describe the same transition.
            identity=(typ,tid or d.get('title'),e['dt'].date())
            if identity in seen:continue
            seen.add(identity)
            row={'date':e['dt'].date().isoformat(),'value':1,'series':d.get('category') or L['unknown'],'category':d.get('category') or L['unknown'],'goal':[g.get('text') or g['id'] for g in mapping.get('readable_mapping',{}).get(tid,{}).get('goals',[])] or [L['unknown']],'priority':d.get('priority') or priorities.get(tid) or L['unknown'],'description':d.get('title') or d.get('task') or str(tid or '')}
            (completed if typ=='tasks_completed' else created).append(row)
        for key,rows in [('tasks_created',created),('tasks_completed',completed)]:result['charts'].append({'id':key,'title':L[key],'method':'sum','type':'bar','rows':rows})
        from unified_bot.integrations.dashboard_progress import progress_charts
        result['charts'].extend(progress_charts(vault, events, cfg))
    elif kind=='calendar':
        source=read_json(data/vault_file('calendar_json'));rows=[]
        for e in source.get('events',[]):
            if e.get('is_allday') or e.get('is_cancelled'):continue
            try:
                # Use normalized local fields; split overnight events at midnight.
                start=datetime.fromisoformat(e['date']+'T'+e['start']);end=datetime.fromisoformat(e.get('end_date',e['date'])+'T'+e['end'])
            except (KeyError,ValueError):continue
            while start<end:
                stop=min(end,datetime.combine(start.date()+timedelta(days=1),datetime.min.time()))
                rows.append({'date':start.date().isoformat(),'value':(stop-start).total_seconds()/3600,'series':e.get('calendar') or L['unknown'],'account':e.get('calendar') or L['unknown'],'category':e.get('activity_type') or L['unknown'],'description':e.get('title','')})
                start=stop
        result.update(filters=['account','category'],note=L['calendar_note'],source_updated=source.get('meta',{}).get('source_captured_at'))
        result['charts']=[{'id':'meeting_hours','title':L['meeting_hours'],'method':'sum','type':'bar','rows':rows}]
        result['charts'].append(dict(id='calendar_activities',title=L['calendar_activities'],type='bar',method='sum',rows=[dict(r,series=r['category']) for r in rows]))
    elif kind=='analytics':
        from shared.obsidian_ui.analytics import analytics_data
        result.update(analytics_data(vault,cfg))
    elif kind=='maintenance':
        from unified_bot.integrations.dashboard_maintenance import maintenance_charts
        result['charts']=maintenance_charts(vault)
    elif kind=='system':
        return read_json(data/cfg['layout']['view_root']/'system.json') or result
    return result


def export_dataset(vault: Path, root: str, kind: str):
    result=build_dataset(vault,kind)
    target=vault/root/(kind+'.json');tmp=target.with_suffix('.tmp')
    tmp.write_text(json.dumps(result,ensure_ascii=False,allow_nan=False));tmp.replace(target)


def refresh_progress(vault: Path):
    """Refresh interactive data independently of Markdown/PNG rendering."""
    from shared.capabilities.sync_steps import sync_step_enabled, STEP_PLANNING_CHARTS
    if not sync_step_enabled(STEP_PLANNING_CHARTS):
        return
    root = f"{folder('dashboards')}/{dashboards_sub('data')}/{ui_config()['layout']['view_root']}"
    (vault/root).mkdir(parents=True, exist_ok=True)
    export_dataset(vault, root, 'progress')


if __name__ == '__main__':
    import argparse
    parser=argparse.ArgumentParser()
    parser.add_argument('--vault', type=Path, required=True)
    args=parser.parse_args()
    refresh_progress(args.vault)
