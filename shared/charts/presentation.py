"""Shared chart styling and explicit weekly aggregation for long histories."""
from datetime import date, timedelta
from collections import Counter
import hashlib
import math
from shared.obsidian_ui.config import ui_config


def category_color(name):
    cfg=ui_config()['chart']
    name=str(name).strip().lower()
    if name in cfg.get('category_colors',{}):return cfg['category_colors'][name]
    palette=cfg['palette']
    index=int.from_bytes(hashlib.sha256(str(name).strip().lower().encode()).digest()[:4],'big')
    return palette[index % len(palette)]


def weekly_counts(days, groups):
    if len(days)<=ui_config()['chart']['weekly_after_days']:
        return days, groups, False
    floor=lambda d:d-timedelta(days=d.weekday())
    result={}
    for name,counts in groups.items():
        acc=Counter()
        for day,count in counts.items():acc[floor(day)]+=count
        result[name]=acc
    return sorted({floor(d) for d in days}),result,True


def weekly_snapshots(rows):
    if len(rows)<=ui_config()['chart']['weekly_after_days']:return rows,False
    grouped={}
    for row in sorted(rows,key=lambda r:r['date']):
        day=date.fromisoformat(row['date']);grouped[day-timedelta(days=day.weekday())]=row
    return list(grouped.values()),True


def polish_chart(fig):
    cfg=ui_config()['chart'];cap=cfg['max_ticks']
    fig.set_size_inches(cfg['figure_width'], max(4.8,fig.get_figheight()))
    for ax in fig.axes:
        # Only thin an explicit set of date/category tick labels. Numeric locators stay intact.
        from matplotlib.ticker import FixedLocator
        if isinstance(ax.xaxis.get_major_locator(),FixedLocator):
            ticks=ax.get_xticks();labels=[x.get_text() for x in ax.get_xticklabels()]
            if len(ticks)==len(labels) and len(ticks)>cap:
                indexes=list(range(0,len(ticks),math.ceil(len(ticks)/cap)))
                ax.set_xticks([ticks[i] for i in indexes], [labels[i] for i in indexes])
        ax.tick_params(axis='both',labelsize=cfg['font_size']-1)
        for label in ax.get_xticklabels():label.set_rotation(0);label.set_horizontalalignment('center')
        ax.title.set_fontsize(cfg['font_size']+1);ax.xaxis.label.set_fontsize(cfg['font_size']);ax.yaxis.label.set_fontsize(cfg['font_size'])
        ax.spines['top'].set_visible(False);ax.spines['right'].set_visible(False)
        legend=ax.get_legend()
        if legend:
            for text in legend.get_texts():text.set_fontsize(cfg['font_size']-1)
    fig.tight_layout()
