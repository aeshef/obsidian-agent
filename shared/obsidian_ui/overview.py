"""Small, escaped dashboard overviews. Detailed analysis belongs in the explorer."""
import html
import json
from collections import defaultdict
from pathlib import Path

from shared.chart_paths import data_path, chart_path
from shared.obsidian_metric_cards import MetricCard, metric_cards_html
from shared.obsidian_ui.config import ui_config


def calendar_overview(analytics: dict) -> str:
    config = ui_config()['overview']
    labels = config['labels']
    days = defaultdict(list)
    for row in (analytics.get('upcoming') or [])[:config['agenda_limit']]:
        days[str(row.get('date') or '')].append(row)
    cards = []
    for day, rows in sorted(days.items()):
        items = ''.join('<div class="au-agenda-event"><time>'+html.escape(f"{r.get('start','')}–{r.get('end','')}")+'</time><span>'+html.escape(str(r.get('title') or ''))+'</span></div>' for r in rows)
        cards.append('<div class="au-agenda-day"><h3>'+html.escape(day)+'</h3>'+items+'</div>')
    agenda = '<div class="au-agenda">'+''.join(cards)+'</div>' if cards else '<p class="au-muted">'+html.escape(labels['empty'])+'</p>'
    parts = ['## '+labels['agenda'], agenda]
    windows = (analytics.get('free_windows') or [])[:config['window_limit']]
    if windows:
        parts += ['## '+labels['free'], metric_cards_html([MetricCard(str(w.get('date') or ''), f"{w.get('start','')}–{w.get('end','')}") for w in windows])]
    # All-day context remains visible without a second collapsed list.
    markers = list({(str(m.get('date','')), str(m.get('title',''))): m for m in analytics.get('day_markers') or []}.values())
    if markers:
        parts += ['<div class="au-day-markers">'+''.join('<span>'+html.escape(str(m.get('date',''))+' · '+str(m.get('title','')))+'</span>' for m in markers)+'</div>']
    return '\n\n'.join(parts)+'\n'


def analytics_overview(vault: Path) -> str:
    labels = ui_config()['overview']['labels']
    path = data_path(vault, 'analytics_insights_json')
    if not path.is_file():
        return ''
    data = json.loads(path.read_text(encoding='utf-8'))
    hypotheses = data.get('hypotheses') or []
    supported = [h for h in hypotheses if h.get('significant_fdr')]
    cards = [MetricCard(labels['evidence'], str(len(supported)), hint=labels['evidence_hint']),
             MetricCard(labels['tested'], str(len(hypotheses))),
             MetricCard(labels['coverage'], f"{data.get('window_days', '—')} {labels['days']}", hint=labels['updated']+' · '+str(data.get('updated','')))]
    report = chart_path(vault, 'chart_analytics_insights_md')
    link = f"\n\n[[{report.relative_to(vault).with_suffix('')}|{labels['evidence_details']}]]" if report.is_file() else ''
    return metric_cards_html(cards)+link+'\n'
