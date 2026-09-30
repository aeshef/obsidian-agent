"""Dashboard chrome and progressive disclosure. No modification of source records."""
from pathlib import Path
import html
import re
from shared.obsidian_ui.assets import install_assets


def present_dashboard(body: str, vault: Path, kind: str) -> str:
    root=install_assets(vault)
    if kind in ('health','progress','calendar','analytics'):
        from unified_bot.integrations.dashboard_datasets import export_dataset
        export_dataset(vault,root,kind)
    if '<!-- assistant-ui -->' in body or 'assistant-ui: true' in body:
        return body
    def bars(match):
        chart=match[1]
        if not chart.strip().startswith('pie'):return match[0]
        values=[(label,float(value)) for label,value in re.findall(r'"([^"\n]+)"\s*:\s*([0-9.]+)',chart)]
        if not values:return match[0]
        maximum=max(v for _,v in values) or 1
        return '<div class="au-section">'+''.join(
            '<div class="au-bar-row"><span>'+html.escape(label)+'</span><div class="au-bar-track"><div class="au-bar-fill" style="width:'+str(100*value/maximum)+'%"></div></div><span class="au-number">'+format(value,',.0f').replace(',',' ')+'</span></div>' for label,value in values)+'</div>'
    def remove_navigation(match):
        first_section=re.search(r'(?m)^## ',body)
        is_intro=first_section is None or match.start()<first_section.start()
        return '' if is_intro and match[0].count('[[')>=3 else match[0]
    body=re.sub(r'(?m)^> \[!abstract\][^\n]*(?:\n>[^\n]*)*\n?', remove_navigation, body)
    body=re.sub(r'(?m)^# [^\n]+\n', '', body, count=1)
    body=re.sub(r'(?m)^```mermaid[ \t]*\n([\s\S]*?)^```[ \t]*$',bars,body)
    # Generated Dataview code is a view asset, not a second source of data.
    section_index=0
    def extract(match):
        nonlocal section_index
        section_index+=1
        code=match[1].strip().replace("Assistant UI/", root+"/")
        name=f"section-{kind}-{section_index}"
        (vault/root/(name+'.js')).write_text(code,encoding='utf-8')
        return f'```dataviewjs\nawait dv.view("{root}/{name}")\n```'
    body=re.sub(r'(?m)^```dataviewjs[ \t]*\n([\s\S]*?)^```[ \t]*$',extract,body)
    appendix=''
    if kind in ('progress','health'):
        from shared.obsidian_ui.config import ui_config
        from shared.obsidian_ui.reports import separate_reports
        body,_=separate_reports(body,ui_config()['labels'])
    # Curated overviews have no legacy folds; keep charts directly below the summary.
    if kind == 'main':
        return '---\ncssclasses: [assistant-dashboard]\nassistant-ui: true\n---\n'+f'```dataviewjs\nawait dv.view("{root}/shell", {{kind: "main"}})\n```\n\n'+body.strip()+'\n'
    if kind in ('finance', 'calendar', 'analytics'):
        prefix='---\ncssclasses: [assistant-dashboard]\nassistant-ui: true\n---\n'
        prefix+=f'```dataviewjs\nawait dv.view("{root}/shell", {{kind: "{kind}"}})\n```\n\n'
        return prefix+body.strip()+f'\n\n```dataviewjs\nawait dv.view("{root}/explorer", {{kind: "{kind}"}})\n```\n'
    # Keep original headings and anchors inside collapsible sections. Never split code.
    lines=body.splitlines(); parts=[]; current=[]; fence=False
    for line in lines:
        if line.startswith('```'):fence=not fence
        if not fence and line.startswith('## ') and current:
            parts.append(current);current=[]
        current.append(line)
    if current:parts.append(current)
    result=[]
    for i,part in enumerate(parts):
        if i>1 and part[0].startswith('## '):
            label=part[0].lstrip('# ').strip()
            result.append('> [!example]- '+label+'\n'+ '\n'.join('> '+line if line else '>' for line in part[1:]))
        else:result.append('\n'.join(part))
    prefix='---\ncssclasses: [assistant-dashboard]\nassistant-ui: true\n---\n'
    prefix+=f'```dataviewjs\nawait dv.view("{root}/shell", {{kind: "{kind}"}})\n```\n\n'
    if kind in ('finance','health','progress','calendar','analytics','system'):
        prefix+=f'```dataviewjs\nawait dv.view("{root}/explorer", {{kind: "{kind}"}})\n```\n\n'
    # A single existing title may remain as an anchor, styled compactly.
    return prefix+'\n\n'.join(result).strip()+'\n\n'+appendix+'\n'
