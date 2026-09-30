"""Separate fixed reports from the interactive dashboard without losing content."""
import re
from shared.vault_paths_config import folder, dashboards_sub


def separate_reports(body: str, labels: dict) -> tuple[str, str]:
    chart_prefix = f"{folder('dashboards')}/{dashboards_sub('charts')}/"
    embed = re.compile(r'!\[\[([^\]\n]+)\]\]')

    def is_chart(match):
        return match[1].split('|')[0].startswith(chart_prefix)

    # Headings inside JS fences are code, not report boundaries.
    blocks, block, fenced = [], [], False
    for line in body.splitlines():
        if re.match(r'^```', line):
            fenced = not fenced
        if not fenced and re.match(r'^#{2,6} ', line) and block:
            blocks.append('\n'.join(block))
            block = []
        block.append(line)
    if block:
        blocks.append('\n'.join(block))
    primary, reports = [], []
    for block in blocks:
        if any(is_chart(m) for m in embed.finditer(block)):
            def link(match):
                if not is_chart(match):
                    return match[0]
                target = match[1].split('|')[0]
                name = target.rsplit('/', 1)[-1]
                name = re.sub(r'\.(png|svg|jpg|md)$', '', name, flags=re.I).replace('_', ' ')
                return '[[' + target + '|' + name + ']]'
            reports.append(embed.sub(link, block).strip())
        else:
            primary.append(block)
    if not reports:
        return body, ''
    content = labels['fixed_reports_note'] + '\n\n' + '\n\n'.join(reports)
    appendix = '> [!note]- ' + labels['fixed_reports'] + '\n' + '\n'.join(
        '> ' + line if line else '>' for line in content.splitlines())
    return '\n\n'.join(primary), appendix
