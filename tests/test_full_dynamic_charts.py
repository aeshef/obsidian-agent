import math
import pytest
from shared.obsidian_ui.series import series_chart
from shared.obsidian_ui.chart_query import query_chart
from shared.obsidian_ui.analysis_query import query_analysis, rho


def test_quarters_keep_true_dates_and_last_balance():
    spec=series_chart('balance','Balance',['2026-01-01','2026-03-31','2026-04-01'],{'Total':[10,20,30]},method='last')
    result=query_chart(spec,'2026-01-01','2026-06-30','quarter',{},366)
    assert result['x']==['2026-01-01','2026-04-01']
    assert result['series'][0]['values']==[20,30]


def test_invalid_and_missing_values_are_not_zero():
    spec=series_chart('weight','Weight',['2026-01-01','2026-01-02','2026-01-03'],{'kg':[0,None,float('nan')]})
    assert [r['value'] for r in spec['rows']]==[0]
    with pytest.raises(ValueError):series_chart('x','x',['2026-01-01'],{'x':[1,2]})


def test_correlations_recomputed_for_period_with_ties_and_no_constant_signal():
    rows=[dict(date=f'2026-01-0{i+1}',a=a,b=b,c=1) for i,(a,b) in enumerate([(1,1),(1,1),(2,2),(3,-3),(4,-4)])]
    spec=dict(type='correlation',rows=rows,metrics=['a','b','c'],min_pairs=3)
    assert query_analysis(spec,'2026-01-01','2026-01-03')['series'][1]['values'][0]==pytest.approx(1)
    assert query_analysis(spec,'2026-01-03','2026-01-05')['series'][1]['values'][0]<0
    assert query_analysis(spec,'2026-01-01','2026-01-03')['series'][2]['values'][0] is None


def test_scatter_lag_can_read_preceding_day_without_expanding_outcome_period():
    spec=dict(type='scatter',rows=[dict(date='2026-01-01',a=3,b=None),dict(date='2026-01-02',a=None,b=4)],metrics=['a','b'],lag=1)
    result=query_analysis(spec,'2026-01-02','2026-01-02')
    assert result['points']==[[3,4,'2026-01-02']]


def test_normalization_keeps_missing_observations():
    spec=dict(type='normalized',metrics=['a','b'],rows=[dict(date=f'2026-01-0{i+1}',a=a,b=b) for i,(a,b) in enumerate([(1,2),(None,2),(3,2)])])
    q=query_analysis(spec,'2026-01-01','2026-01-03')
    assert q['series'][0]['values']==[-1,None,1]
    assert q['series'][1]['values']==[None,None,None]
