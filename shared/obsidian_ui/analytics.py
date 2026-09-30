"""Interactive views of the canonical daily panel and Life OS scores."""
import csv
import json
from shared.chart_paths import data_path
from shared.obsidian_ui.series import finite, series_chart


def analytics_data(vault, cfg):
    from shared.analytics.vault_analytics_config import vault_analytics_config
    from shared.analytics.sleep_debt import compute_sleep_debt_series
    L=cfg['labels'];config=vault_analytics_config()
    path=data_path(vault,'master_daily_panel_csv')
    rows=[]
    if path.is_file():
        with path.open() as f:
            rows=[{k:(v if k=='date' else finite(v)) for k,v in r.items()} for r in csv.DictReader(f)]
    dates=[r['date'] for r in rows];charts=[]
    for spec in cfg['interactive']['panel_charts']:
        charts.append(series_chart(spec['id'],L[spec['id']],dates,
            {L.get(k,k):[r.get(k) for r in rows] for k in spec['metrics']},
            method=spec.get('method','mean'),chart_type=spec.get('type','line'),smooth=True))
    debt_cfg=config.get('sleep_debt') or {}
    debt=compute_sleep_debt_series(rows,target_hours=debt_cfg.get('target_hours',8),decay=debt_cfg.get('decay',.9))
    charts.append(series_chart('sleep_debt',L['sleep_debt'],[r['date'] for r in debt],
        {L['sleep_debt']:[None if r.get('missing') else r['debt'] for r in debt]},method='last'))
    life_path=data_path(vault,'life_os_daily_json')
    life=json.loads(life_path.read_text()).get('rows',[]) if life_path.is_file() else []
    charts.append(series_chart('life_scores',L['life_scores'],[r['date'] for r in life],
        {L[k]:[r.get(k) for r in life] for k in ('capacity','output','drain')}))
    charts.append(dict(id='life_regimes',title=L['life_regimes'],type='bar',method='sum',
        rows=[dict(date=r['date'],series=L.get(r['regime'],r['regime']),value=1) for r in life]))
    metrics=[k for k in cfg['interactive']['panel_metrics'] if any(finite(r.get(k)) is not None for r in rows)]
    for cid,kind in [('panel_correlation','correlation'),('panel_relationship','scatter'),('panel_normalized','normalized')]:
        charts.append(dict(id=cid,title=L[cid],type=kind,method='mean',rows=rows,metrics=metrics,
                           min_pairs=config.get('panel',{}).get('min_pairs',8)))
    # Lagged sleep vs next-day outcomes is selectable with the same raw observations.
    return dict(charts=charts)
