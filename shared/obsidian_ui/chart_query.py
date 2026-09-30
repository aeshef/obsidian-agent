"""Validated chart queries for on-demand exports. Mirrors browser bucket semantics."""
from collections import defaultdict
from datetime import date, timedelta
from statistics import median


def bucket(day, grain):
    d=date.fromisoformat(day)
    if grain=='week':d-=timedelta(days=d.weekday())
    if grain=='month':d=d.replace(day=1)
    if grain=='quarter':d=d.replace(month=(d.month-1)//3*3+1,day=1)
    return d.isoformat()


def query_chart(spec, start, end, grain, filters, max_days):
    a,b=date.fromisoformat(start),date.fromisoformat(end)
    if a>b or (b-a).days>max_days:raise ValueError('invalid_date_range')
    if grain not in ('day','week','month','quarter','auto'):raise ValueError('invalid_grain')
    if grain=='auto':grain='month' if (b-a).days>180 else 'week' if (b-a).days>45 else 'day'
    if spec['type'] in ('correlation','scatter','normalized'):
        if filters:raise ValueError('unsupported_filter')
        from shared.obsidian_ui.analysis_query import query_analysis
        return query_analysis(spec,start,end)
    supported=spec.get('filter_fields')
    if supported is not None and any(k not in supported for k,v in filters.items() if v):raise ValueError('unsupported_filter')
    rows=[]
    for r in spec['rows']:
        if not spec.get('snapshot') and not start<=r['date']<=end:continue
        if any(v not in (r.get(k) if isinstance(r.get(k),list) else [r.get(k)]) for k,v in filters.items() if v):continue
        rows.append(r)
    if not rows:raise ValueError('no_data')
    categorical=spec['type'] in ('categorical','heatmap')
    groups=defaultdict(list)
    for r in sorted(rows,key=lambda r:r['date']):
        x=r['x'] if categorical else bucket(r['date'],grain)
        groups[(x,r['series'])].append(r['value'])
    method=spec['method'];values={}
    for k,nums in groups.items():
        values[k]=median(nums) if method=='median' else nums[-1] if method=='last' else sum(nums)/len(nums) if method=='mean' else sum(nums)
    xs=sorted({k[0] for k in values})
    if not categorical:
        xs=[];d=date.fromisoformat(bucket(start,grain))
        while d<=b:
            xs.append(d.isoformat())
            if grain=='quarter':
                d=date(d.year+1,1,1) if d.month==10 else date(d.year,d.month+3,1)
                continue
            d=(date(d.year+1,1,1) if d.month==12 else date(d.year,d.month+1,1)) if grain=='month' else d+timedelta(days=7 if grain=='week' else 1)
    names=sorted({k[1] for k in values})
    return dict(x=xs,series=[dict(name=n,values=[values.get((x,n),0 if categorical else None) for x in xs]) for n in names],grain=grain,rows=len(rows))
