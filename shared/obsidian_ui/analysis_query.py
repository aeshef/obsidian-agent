"""Server-side equivalents of the browser's correlation, scatter and z-score views."""
from datetime import date,timedelta
import math
from shared.obsidian_ui.series import finite


def standardized(values):
    nums=[v for v in values if finite(v) is not None]
    if not nums:return [None]*len(values)
    mean=sum(nums)/len(nums);sd=math.sqrt(sum((x-mean)**2 for x in nums)/len(nums))
    return [(x-mean)/sd if finite(x) is not None and sd else None for x in values]


def rho(points):
    def ranks(nums):
        return [sum(v<x for v in nums)+(sum(v==x for v in nums)+1)/2 for x in nums]
    x=standardized(ranks([p[0] for p in points]));y=standardized(ranks([p[1] for p in points]))
    return sum(a*b for a,b in zip(x,y))/len(x) if len(x)>1 and all(v is not None for v in x+y) else None


def query_analysis(spec,start,end):
    rows=[r for r in spec['rows'] if start<=r['date']<=end];metrics=spec['metrics']
    if not rows or len(metrics)<2:raise ValueError('no_data')
    kind=spec['type'];x=spec.get('x_metric') or metrics[0];y=spec.get('y_metric') or metrics[1]
    if x not in metrics or y not in metrics:raise ValueError('invalid_metric')
    lag=spec.get('lag',0)
    if lag not in (0,1,2,3,7):raise ValueError('invalid_lag')
    lookup={r['date']:r for r in spec['rows']}
    def pairs(x,y,lag=0):
        out=[]
        for r in rows:
            day=(date.fromisoformat(r['date'])-timedelta(days=lag)).isoformat()
            a=finite(lookup.get(day,{}).get(x));b=finite(r.get(y))
            if a is not None and b is not None:out.append([a,b,r['date']])
        return out
    result=dict(grain='day',rows=len(rows),x=[],series=[])
    if kind=='scatter':
        result.update(points=pairs(x,y,lag),x_metric=x,y_metric=y)
    elif kind=='normalized':
        result.update(x=[r['date'] for r in rows],series=[dict(name=k,values=standardized([r.get(k) for r in rows])) for k in [x,y]])
    else:
        values=[]
        for y in metrics:
            vals=[]
            for x in metrics:
                p=pairs(x,y);vals.append(rho(p) if len(p)>=spec['min_pairs'] else None)
            values.append(dict(name=y,values=vals))
        result.update(x=metrics,series=values)
    return result
