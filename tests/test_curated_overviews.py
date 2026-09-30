from shared.obsidian_ui.overview import calendar_overview


def test_agenda_escapes_event_names_and_preserves_time():
    body = calendar_overview({'upcoming':[{'date':'2026-01-01','start':'09:00','end':'10:00','title':'<script> & meeting'}], 'day_markers':[{'date':'2026-01-01','title':'<holiday>'}]})
    assert '<script>' not in body
    assert '&lt;script&gt; &amp; meeting' in body
    assert '09:00–10:00' in body
    assert '&lt;holiday&gt;' in body
    assert '> [!' not in body


def test_finance_dashboard_does_not_repeat_legacy_sections():
    from finance_bot.bot.services.dashboard.assemble import assemble_dashboard_markdown
    body = assemble_dashboard_markdown(part_summary=['SUMMARY'],part_planned=['PLAN'],**{k:['LEGACY'] for k in ['part_structure','part_exp_pies','part_badge','part_oneoff_list','part_moves','part_exp_by_account','part_balances','part_top_exp']})
    assert 'SUMMARY' in body and 'PLAN' in body
    assert 'LEGACY' not in body
