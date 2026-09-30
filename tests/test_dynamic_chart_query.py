import pytest
from shared.obsidian_ui.chart_query import query_chart


def spec(rows, **kwargs):
    return dict(type='line',method='sum',rows=rows,**kwargs)


def test_median_uses_raw_tasks_not_weekly_medians():
    rows=[dict(date='2026-09-01',series='lead',value=v) for v in [1,2,3,100]]
    rows.append(dict(date='2026-09-08',series='lead',value=99))
    s=spec(rows);s['method']='median'
    assert query_chart(s,'2026-09-01','2026-09-30','month',{},366)['series'][0]['values']==[3]


def test_date_range_and_filters_are_applied_before_aggregation():
    rows=[dict(date=d,series='done',value=v,category=c) for d,v,c in [('2026-09-01',10,'a'),('2026-09-02',2,'a'),('2026-09-02',50,'b')]]
    q=query_chart(spec(rows),'2026-09-02','2026-09-03','day',{'category':'a'},366)
    assert q['series'][0]['values']==[2,None]


def test_current_snapshot_does_not_pretend_to_be_historical():
    s=spec([dict(date='2026-09-28',series='old',x='work',value=3)],snapshot='2026-09-28',filter_fields=[])
    s['type']='categorical'
    assert query_chart(s,'2025-01-01','2025-01-02','day',{},366)['series'][0]['values']==[3]
    with pytest.raises(ValueError,match='unsupported_filter'):query_chart(s,'2025-01-01','2025-01-02','day',{'goal':'x'},366)


def test_invalid_range_and_empty_results_fail_explicitly():
    s=spec([])
    with pytest.raises(ValueError,match='invalid_date_range'):query_chart(s,'2026-01-02','2026-01-01','day',{},366)
    with pytest.raises(ValueError,match='no_data'):query_chart(s,'2026-01-01','2026-01-02','day',{},366)
