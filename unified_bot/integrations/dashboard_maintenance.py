"""History-based maintenance charts; daily counts and point-in-time sizes stay distinct."""
from shared.obsidian_ui.series import series_chart


def maintenance_charts(vault):
    from knowledge_bot.services.maintenance_metrics import load_history
    from functools import partial
    from shared.domain_messages import dmsg
    mm=partial(dmsg,"knowledge_maintenance")
    rows=load_history(vault,max_rows=None);dates=[r['date'] for r in rows]
    def values(section,key,scale=1):
        return [None if (r.get(section) or {}).get(key) is None else r[section][key]/scale for r in rows]
    return [
        series_chart('maintenance_notes',mm('chart_notes_title'),dates,{mm('chart_notes_before'):values('before','notes_md_db700'),mm('chart_notes_after'):values('after','notes_md_db700')},method='last'),
        series_chart('maintenance_storage',mm('chart_export_title'),dates,{mm('chart_export_title'):values('before','bytes_export',1024*1024)},method='last',unit='MB'),
        series_chart('maintenance_queue',mm('chart_queue_title'),dates,{mm('chart_queue_title'):values('before','reprocess_eligible')},method='last'),
        series_chart('maintenance_actions',mm('chart_daily_title'),dates,{'retag':values('run','retag_touched'),mm('chart_bar_reprocess'):values('run','reprocess_saved'),mm('chart_bar_empty'):values('run','reprocess_deleted_empty')},method='sum',chart_type='bar'),
        series_chart('maintenance_freed',mm('chart_bar_dup'),dates,{mm('chart_bar_dup'):values('run','duplicates_mb_freed')},method='sum',unit='MB'),
    ]
