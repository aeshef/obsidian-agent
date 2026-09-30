"""Read-only dashboard export. Uses the same exclusions as spending analytics."""
from pathlib import Path
from datetime import datetime
import json
from shared.finance.currency import base_currency, is_base_currency
from shared.obsidian_ui.assets import install_assets
from shared.charts.presentation import category_color
from bot.services.dashboard.filters import (resolve_exclude_spending_categories, resolve_badge_category,
    is_badge_expense, is_excluded_category, resolve_badge_account_name, skip_badge_account)


def export_presentation(vault: Path, transactions: list[dict], accounts: list[dict], charts=None, oneoff_threshold=None):
    root=install_assets(vault)
    excluded=resolve_exclude_spending_categories();badge=resolve_badge_category()
    by_id={a['id']:a for a in accounts};badge_account=resolve_badge_account_name()
    rows=[]
    for t in transactions:
        if t['type'] not in ('expense','income') or not is_base_currency(t.get('currency')):
            continue
        if is_excluded_category(t,excluded) or is_badge_expense(t,badge) or skip_badge_account(t['account_id'],by_id,badge_account):
            continue
        rows.append({'id':t['id'],'date':str(t['occurred_at'])[:10], 'type':t['type'],
                     'amount':float(t['amount']), 'category':t.get('category') or '—',
                     'description':t.get('description') or '', 'account':t.get('account_name') or by_id.get(t['account_id'],{}).get('name') or '—'})
    result={'generated_at':datetime.now().astimezone().isoformat(timespec='minutes'),
            'currency':base_currency(),'latest_date':max((t['date'] for t in rows),default=None), 'transactions':rows, 'category_colors':{t['category']:category_color(t['category']) for t in rows}}
    from shared.obsidian_ui.config import ui_config
    cfg=ui_config();L=cfg['labels']
    result.update(filters=['account','category'], note=L['finance_note'])
    result['charts']=[dict(id=t,title=L[t],unit=base_currency(),type='bar',method='sum',
                          max_series=cfg['interactive']['max_series'],
                          rows=[dict(r,value=r['amount'],series=r['category']) for r in rows if r['type']==t])
                      for t in ('expense','income')]+list(charts or [])
    if oneoff_threshold is not None:
        for cid,large in [('regular_spending',False),('oneoff_spending',True)]:
            result['charts'].insert(-len(charts) if charts else len(result['charts']),dict(
                id=cid,title=L[cid],unit=base_currency(),type='bar',method='sum',
                max_series=cfg['interactive']['max_series'],
                note=L['spending_threshold'].format(threshold=oneoff_threshold,currency=base_currency()),
                rows=[dict(r,value=r['amount'],series=r['category']) for r in rows
                      if r['type']=='expense' and (r['amount']>=oneoff_threshold)==large]))
    result['charts'].append(dict(id='cash_flow',title=L['cash_flow'],unit=base_currency(),type='line',method='sum',
        rows=[dict(r,value=r['amount'],series=L[r['type']]) for r in rows]))
    dest=vault/root/'finance.json'  ;temp=dest.with_suffix('.tmp')
    temp.write_text(json.dumps(result,ensure_ascii=False),encoding='utf-8');temp.replace(dest)
