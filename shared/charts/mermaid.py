"""Mermaid chart snippets (Obsidian-compatible)."""
from __future__ import annotations

from shared.domain_messages import dmsg


def mermaid_pie(labels_values: list[tuple[str, float]], title: str) -> str:
    """Mermaid pie chart."""
    if not labels_values:
        no_data = dmsg("charts", "no_data")
        return f'pie\n    title {title}\n    "{no_data}" : 1'
    # Do not use showData: Obsidian/Mermaid adds raw values in [...],
    # we already print readable amounts/percentages in the label.
    lines = [f'pie\n    title {title}']
    for label, val in labels_values:
        safe_label = label.replace('"', "'")[:60]
        lines.append(f'    "{safe_label}" : {max(0, round(val, 2))}')
    return "\n".join(lines)


def mermaid_xychart_lines(
    x_labels: list[str],
    series: dict[str, list[float]],
    title: str,
    y_label: str | None = None,
) -> str:
    """Mermaid xychart-beta with multiple lines."""
    y_label = y_label or dmsg("charts", "y_label_sum")
    if not x_labels or not series:
        return dmsg("charts", "insufficient_data", title=title)
    max_y = 1
    for vals in series.values():
        if vals:
            max_y = max(max_y, max(vals), -min(vals))
    max_y = int(max_y * 1.2) + 1
    lines = [
        "xychart-beta",
        f'    title "{title}"',
        f"    x-axis [{', '.join(x_labels)}]",
        f'    y-axis "{y_label}" 0 --> {max_y}',
    ]
    for name, vals in series.items():
        safe_name = name.replace('"', "'")[:25]
        vals_str = ", ".join(str(round(v, 2)) for v in vals)
        lines.append(f'    line "{safe_name}" [{vals_str}]')
    return "\n".join(lines)
