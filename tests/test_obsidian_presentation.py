from datetime import date, timedelta
from pathlib import Path
from collections import Counter


def test_weekly_aggregation_preserves_totals():
    from shared.charts.presentation import weekly_counts,weekly_snapshots
    days=[date(2026,1,1)+timedelta(days=i) for i in range(90)]
    original={'a':Counter({d:i for i,d in enumerate(days)})}
    weeks,aggregated,changed=weekly_counts(days,original)
    assert changed and len(weeks)<len(days)
    assert sum(aggregated['a'].values())==sum(original['a'].values())
    snapshots=[{'date':d.isoformat(),'total':i} for i,d in enumerate(days)]
    reduced,changed=weekly_snapshots(snapshots)
    assert changed and reduced[-1]==snapshots[-1]
    assert all(r in snapshots for r in reduced)
    assert len(snapshots)==90


def test_color_does_not_depend_on_order():
    from shared.charts.presentation import category_color
    assert category_color('Health')==category_color(' health ')
    a=category_color('Health');category_color('Work');assert category_color('Health')==a


def test_dashboard_html_and_code_are_preserved(tmp_path,monkeypatch):
    from shared.obsidian_ui import layout
    monkeypatch.setattr(layout,'install_assets',lambda v:'ui')
    (tmp_path/'ui').mkdir()
    body='# Header\n\n## Summary\ntext\n\n### Detail\n```dataviewjs\nconst x="## literal";dv.paragraph(x)\n```\n\n## Later\nsource'
    result=layout.present_dashboard(body,tmp_path,'finance')
    assert 'cssclasses: [assistant-dashboard]' in result
    assert '> [!example]- Detail' not in result
    assert '### Detail' in result
    assert (tmp_path/'ui/section-finance-1.js').read_text()=='const x="## literal";dv.paragraph(x)'
    assert layout.present_dashboard(result,tmp_path,'finance')==result
    pie='```mermaid\npie\n"<unsafe>" : 10\n"other" : 5\n```'
    rendered=layout.present_dashboard(pie,tmp_path,'finance')
    assert '&lt;unsafe&gt;' in rendered and '<unsafe>' not in rendered


def test_finance_export_respects_exclusions_currency_and_badge(tmp_path,monkeypatch):
    from bot.services.dashboard import presentation_data as p
    import json
    (tmp_path/'ui').mkdir()
    monkeypatch.setattr(p,'install_assets',lambda v:'ui')
    monkeypatch.setattr(p,'resolve_exclude_spending_categories',lambda:{'Transfer'})
    monkeypatch.setattr(p,'resolve_badge_category',lambda:'Badge')
    monkeypatch.setattr(p,'resolve_badge_account_name',lambda:'Badge account')
    monkeypatch.setattr(p,'is_base_currency',lambda c:c=='RUB')
    row={'id':1,'type':'expense','account_id':1,'occurred_at':'2026-09-23','amount':12.34,'currency':'RUB','category':'Food'}
    rows=[row,dict(row,id=2,category='Transfer'),dict(row,id=3,currency='USD'),dict(row,id=4,category='Badge'),dict(row,id=5,account_id=2)]
    p.export_presentation(tmp_path,rows,[{'id':1,'name':'Card'},{'id':2,'name':'Badge account'}])
    output=json.loads((tmp_path/'ui/finance.json').read_text())
    assert len(output['transactions'])==1
    assert output['transactions'][0]['amount']==12.34
    assert output['latest_date']=='2026-09-23'


def test_fence_inside_javascript_does_not_truncate_view(tmp_path, monkeypatch):
    from shared.obsidian_ui import layout
    monkeypatch.setattr(layout, 'install_assets', lambda v: 'ui')
    (tmp_path/'ui').mkdir()
    code = 'const re = /```json\\n([\\s\\S]*?)\\n```/gm;\nasync function read() { return "ok"; }\nawait read();'
    body = '## Parent\n\n### Child\n```dataviewjs\n'+code+'\n```\n\n## Other\ncontent'
    result = layout.present_dashboard(body, tmp_path, 'main')
    assert (tmp_path/'ui/section-main-1.js').read_text() == code
    assert 'async function read' not in result
    assert '[!example]- Child' not in result


def test_audit_summary_callouts_are_not_removed(tmp_path,monkeypatch):
    from shared.obsidian_ui import layout
    monkeypatch.setattr(layout,'install_assets',lambda v:'ui')
    (tmp_path/'ui').mkdir()
    body='# Audit\n\n## Duplicates\n> [!abstract] Summary\n> 3485 notes; 0 duplicate groups\n'
    assert '3485 notes' in layout.present_dashboard(body,tmp_path,'vault_audit')


def test_static_reports_are_links_and_keep_unique_content(monkeypatch):
    from shared.obsidian_ui import reports
    monkeypatch.setattr(reports, 'folder', lambda _: 'Dashboards')
    monkeypatch.setattr(reports, 'dashboards_sub', lambda _: 'Charts')
    body = "## Plan\nKeep this summary\n\n## Balance\n![[Dashboards/Charts/Balance.png]]\nBalance caption\n\n### Flows\n![[Dashboards/Charts/Flows]]\n\n## Notes\n![[Notes/Important]]\n"
    main, appendix = reports.separate_reports(body, {'fixed_reports': 'Reports', 'fixed_reports_note': 'Independent dates'})
    assert 'Keep this summary' in main and '![[Notes/Important]]' in main
    assert 'Balance' not in main and 'Flows' not in main
    assert '[[Dashboards/Charts/Balance.png|Balance]]' in appendix
    assert '[[Dashboards/Charts/Flows|Flows]]' in appendix
    assert '![[Dashboards/Charts/' not in appendix
    assert 'Balance caption' in appendix and 'Independent dates' in appendix
