"""Export read-only knowledge views to the existing mobile mirror, without raw attachments."""
from pathlib import Path
import argparse
import json
import shutil
from shared.obsidian_ui.config import ui_config
from shared.vault_paths_config import folder, dashboards_sub
from shared.vault_layout import knowledge_subdir


def export(source: Path, destination: Path):
    if source.resolve()==destination.resolve():raise ValueError('source and destination must differ')
    root=f"{folder('dashboards')}/{dashboards_sub('data')}/{ui_config()['layout']['view_root']}"
    cfg_path=destination/root/'config.json'
    if not cfg_path.is_file():return
    cfg=json.loads(cfg_path.read_text());cfg['read_only_mirror']=True
    cfg.pop('executor',None)
    cfg_path.write_text(json.dumps(cfg,ensure_ascii=False),encoding='utf-8')
    kb=knowledge_subdir();local=source/kb
    # Do not delete mobile notes. Existing originals remain authoritative on Mac.
    for path in local.rglob('*.md'):
        if any(part.startswith('.') or part in ('_Вложения','_Attachments') for part in path.relative_to(local).parts):continue
        target=destination/path.relative_to(source);target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists() or target.stat().st_mtime<path.stat().st_mtime:shutil.copy2(path,target)
    quickadd=destination/'.obsidian/plugins/quickadd/data.json'
    if quickadd.is_file():
        settings=json.loads(quickadd.read_text())
        settings['choices']=[c for c in settings.get('choices',[]) if not str(c.get('id','')).startswith('assistant-') or c.get('id')=='assistant-check-data']
        quickadd.write_text(json.dumps(settings,ensure_ascii=False),encoding='utf-8')


if __name__=='__main__':
    ap=argparse.ArgumentParser();ap.add_argument('--source',type=Path,required=True);ap.add_argument('--destination',type=Path,required=True)
    args=ap.parse_args();export(args.source,args.destination)
