"""Portable chart specs shared by dashboard producers and on-demand exports."""
import math


def finite(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def series_chart(chart_id, title, dates, series, *, method='mean', chart_type='line', **options):
    rows=[]
    for name, values in series.items():
        if len(dates)!=len(values):raise ValueError("series_length_mismatch")
        for day, raw in zip(dates, values):
            value=finite(raw)
            if value is not None:
                rows.append(dict(date=str(day)[:10], series=name, value=value))
    return dict(id=chart_id,title=title,type=chart_type,method=method,rows=rows,**options)
