from pathlib import Path
import json
import yaml
from shared.obsidian_ui.assets import install_assets
from shared.vault_paths_config import vault_rel_path


def build_library(vault: Path):
    root=install_assets(vault)
    cfg=json.loads((vault/root/'config.json').read_text());L=cfg['labels'];kb=cfg['knowledge_folder']
    paths=cfg['paths']
    if 'library' not in paths:return
    base={'filters':{'and':['file.ext == "md"', f'file.inFolder("{kb}")', *[f'!file.path.contains("/{vault_rel_path(key)}/")' for key in ('knowledge_attachments', 'knowledge_hubs')]]},
          'properties':{'file.name':{'displayName':L['catalog']},'file.mtime':{'displayName':L['recent']}},
          'views':[{'type':'cards','name':L['recent'],'limit':cfg['layout']['recent_limit'],'order':['file.name','type','status','file.mtime'],'sort':[{'property':'file.mtime','direction':'DESC'}]},
                   {'type':'table','name':L['catalog'],'order':['file.name','type','status','tags','source','file.mtime'],'sort':[{'property':'file.mtime','direction':'DESC'}]},
                   {'type':'table','name':L['projects'],'filters':{'and':['type == "project"']},'order':['file.name','status','file.mtime']}]}
    (vault/root/'Library.base').write_text(yaml.safe_dump(base,allow_unicode=True,sort_keys=False),encoding='utf-8')
    notes=['---','cssclasses: [assistant-dashboard, assistant-library]','assistant-ui: true','---','```dataviewjs',f'await dv.view("{root}/shell", {{kind: "library"}})','```','']
    actions=[('idea',L['new_note']),('material',L['new_material']),('project',L['new_project'])]
    notes.append(' '.join('`BUTTON[assistant-'+key+']`' for key,_ in actions));notes+=['',f'![[{root}/Library.base]]','']
    for key,label in actions:
        block={'id':'assistant-'+key,'label':label,'style':'primary' if key=='idea' else 'default','hidden':True,'action':{'type':'command','command':'quickadd:choice:assistant-'+key}}
        notes+=['```meta-bind-button',yaml.safe_dump(block,allow_unicode=True,sort_keys=False).strip(),'```','']
    from shared.obsidian_ui.quickadd import quickadd_choices
    quickadd_choices(vault, root)
    (vault/paths['library']).write_text('\n'.join(notes),encoding='utf-8')
