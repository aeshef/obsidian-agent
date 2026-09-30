"""Kanban chart specifications from domain records, independent of rendering."""
from datetime import date, datetime
import json
from shared.chart_paths import chart_path
from planning_bot.core.pdmsg import pdmsg


def progress_charts(vault, events, cfg):
    from planning_bot.core.config import KANBAN_COLUMNS, IN_WORK_COLUMN, DONE_COLUMN, BLOCKED_COLUMN
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.services.kanban_flow.timelines import build_task_timelines
    from shared.agent.platform_config import platform_int
    L = cfg['labels']
    def read(key):
        p = chart_path(vault, key)
        return json.loads(p.read_text()) if p.is_file() else {}
    metrics = read('kanban_flow_metrics_json')
    history = read('kanban_columns_history_json').get('snapshots', [])
    open_history = read('open_tasks_history_json').get('snapshots', [])
    charts = []
    def add(key, title, rows, method='sum', type='line', **kwargs):
        charts.append(dict(id=key, title=title, rows=rows, method=method, type=type,
                           filter_fields=[], **kwargs))
    def row(day, value, series, **extra):
        return dict(date=day, value=value, series=series, **extra)
    add('tasks_open', L['tasks_open'], [row(s['date'], v, k, category=k)
        for s in open_history for k,v in s.get('by_category', {}).items()], 'last')
    charts[-1]['filter_fields']=['category']
    daily=metrics.get('daily_flow', [])
    add('flow', L['flow_title'], [row(s['date'],s[k],pdmsg(label))
        for s in daily for k,label in [('arrivals','kanban_flow_label_arrivals'),('departures','kanban_flow_label_departures')]], type='bar', stack=False)
    add('flow_debt', pdmsg('kanban_flow_label_flow_debt'), [row(s['date'],s['flow_debt'],pdmsg('kanban_flow_label_flow_debt')) for s in daily], 'last', note=L['flow_debt_note'])
    totals={'arrivals':0,'departures':0}; cumulative=[]
    for s in daily:
        for k,label in [('arrivals','kanban_flow_label_arrivals'),('departures','kanban_flow_label_departures')]:
            totals[k]+=s[k];cumulative.append(row(s['date'],totals[k],pdmsg(label)))
    add('flow_cumulative', L['flow_cumulative'], cumulative, 'last', note=L['cumulative_note'])
    add('cfd',pdmsg('kanban_flow_chart_cfd_title'),[row(s['date'],s.get('by_column',{}).get(k,0),k) for s in history for k in KANBAN_COLUMNS[:-1]],'last',area=True,stack=True)
    segments=['goal_mapped','unmapped','daily_routine']
    add('wip_segments',pdmsg('kanban_flow_chart_wip_segments_title'),[row(s['date'],s.get('by_goal_segment',{}).get(k,0),pdmsg('kanban_flow_segment_'+k)) for s in history for k in segments],'last',area=True,stack=True)
    add('goal_completions',pdmsg('kanban_flow_chart_goal_mapping_title'),[row(s['date'],s.get(k,0),pdmsg('kanban_flow_segment_'+k)) for s in metrics.get('completions_by_goal_segment',[]) for k in segments],type='bar')
    reliable=(metrics.get('period') or {}).get('start','')
    effective=[e for e in events if e['dt'].date().isoformat()>=reliable]
    timelines=build_task_timelines(effective,in_work_column=IN_WORK_COLUMN,done_column=DONE_COLUMN)
    limit=platform_int('planning_kanban_flow','lead_time_max_days',default=365)
    durations=[]
    for t in timelines.values():
        if not t.get('done_at') or not t.get('task_id'):continue
        for key,label in [('created_at','kanban_flow_label_lead_p50'),('in_work_at','kanban_flow_label_cycle_p50')]:
            if not t.get(key):continue
            value=(t['done_at']-t[key]).total_seconds()/86400
            if 0<=value<=limit:durations.append(row(t['done_at'].date().isoformat(),value,pdmsg(label),description=t['title']))
    add('lead_cycle',L['lead_cycle_title'],durations,'median',unit=L['day'],note=L['lead_cycle_note'])
    transitions=[]
    for e in effective:
        d=e.get('data') or {}
        if e.get('type')=='task_moved' and d.get('from') and d.get('to'):
            transitions.append(row(e['dt'].date().isoformat(),1,d['to'],x=d['from'],description=d.get('title','')))
    add('transitions',pdmsg('kanban_flow_chart_transitions_title'),transitions,type='heatmap')
    from shared.vault_paths_config import folder, vault_file
    board_path = vault / folder("tasks") / vault_file("kanban_board")
    tasks = KanbanBoard(board_path).get_tasks(exclude_today=False, exclude_blocked=False) if board_path.is_file() else []
    today=date.today().isoformat();aging=[];horizon=[];due_dates=[]
    deadlines={}
    for t in tasks:
        dl=t.get('deadline') or '';tid=(t.get('task_id') or '').lower()
        try:deadline=date.fromisoformat(dl[:10])
        except ValueError:deadline=None
        if deadline:deadlines[tid]=deadline
        if t.get('completed') or t.get('column') not in KANBAN_COLUMNS[:-1]:continue
        try:age=(date.today()-date.fromisoformat(t.get('created_date','')[:10])).days
        except (ValueError,TypeError):age=None
        bucket='unknown' if age is None or age<0 else '0_7' if age<=7 else '8_14' if age<=14 else '15_30' if age<=30 else '31_plus'
        label=L['unknown'] if bucket=='unknown' else pdmsg('kanban_flow_aging_'+bucket)
        common=dict(category=t.get('category') or L['unknown'],description=t.get('title',''),column=t.get('column'),in_work=t.get('column')==IN_WORK_COLUMN,blocked=t.get('column')==BLOCKED_COLUMN)
        aging.append(row(today,1,label,x=common['category'],**common))
        status='no_deadline' if not deadline else 'overdue' if deadline<date.today() else 'today' if deadline==date.today() else 'week' if (deadline-date.today()).days<=cfg['interactive']['deadline_horizon_days'] else 'later'
        horizon.append(row(today,1,L['deadline_'+status],x=L['deadline_'+status],**common))
        if deadline:due_dates.append(row(deadline.isoformat(),1,L['deadline_'+status],x=deadline.isoformat(),**common))
    add('aging',pdmsg('kanban_flow_chart_aging_title'),[dict(r,x=r['series']) for r in aging],type='categorical',snapshot=today)
    add('aging_category',pdmsg('kanban_flow_chart_cemetery_title'),aging,type='categorical',snapshot=today)
    for c in charts[-2:]:c['filter_fields']=['category']
    add('deadline_horizon',L['deadline_horizon'],horizon,type='categorical',snapshot=today)
    charts[-1]['filter_fields']=['category']
    add('deadline_dates', L['deadline_dates'], sorted(due_dates, key=lambda r:r['date']), type='categorical', snapshot=today, horizontal=True, note=L['deadline_dates_note'])
    charts[-1]['filter_fields']=['category']
    completed=[]
    for t in timelines.values():
        if not t.get('done_at'):continue
        done=t['done_at'].date();dl=deadlines.get(t.get('task_id','').lower())
        status='no_deadline' if dl is None else 'early' if done<dl else 'on_day' if done==dl else 'late'
        label=pdmsg('kanban_flow_deadline_'+('none' if status=='no_deadline' else status))
        completed.append(row(done.isoformat(),1,label,x=label,description=t['title']))
    add('deadline_completion',pdmsg('kanban_flow_chart_deadline_blitz_title'),completed,type='categorical',note=L['deadline_coverage_note'])
    for c in charts:
        if not c.get('snapshot') and c['id']!='deadline_dates':c['source_updated']=metrics.get('generated_at')
    return charts
