from pathlib import Path
import json


def quickadd_choices(vault: Path, root: str):
    cfg=json.loads((vault/root/'config.json').read_text());L=cfg['labels'];kb=cfg['knowledge_folder']
    template_folder=vault/root/'templates';template_folder.mkdir(exist_ok=True)
    choices=[]
    for key,kind,label in [('idea','idea',L['new_note']),('material','article',L['new_material']),('project','project',L['new_project'])]:
        title='{{VALUE:'+L['idea_title']+'}}'
        content='---\ntype: '+kind+'\nstatus: '+('active' if key=='project' else 'inbox')+'\ncreated: {{DATE:YYYY-MM-DD}}\ntags: []\n---\n\n# '+title+'\n\n'
        if key=='material':content+='{{VALUE:'+L['material_url']+'}}\n\n'
        content+='{{VALUE:'+L['idea_body']+'|type:multiline}}\n'
        (template_folder/(key+'.md')).write_text(content,encoding='utf-8')
        choices.append({'id':'assistant-'+key,'name':label,'type':'Template','command':True,'templatePath':root+'/templates/'+key+'.md',
          'fileNameFormat':{'enabled':True,'format':'{{DATE:YYYYMMDD-HHmmss}} '+title},
          'folder':{'enabled':True,'folders':[kb+'/_Inbox' if key!='project' else kb+'/Projects'],'chooseWhenCreatingNote':False,'createInSameFolderAsActiveFile':False,'chooseFromSubfolders':False},
          'appendLink':False,'openFile':True,'fileOpening':{'location':'tab','direction':'vertical','mode':'default','focus':True},'fileExistsBehavior':{'kind':'prompt'}})
    for key,label in [('link-project',L['link_project']),('check-data',L['check'])]:
        choices.append({'id':'assistant-'+key,'name':label,'type':'Macro','command':True,'runOnStartup':False,
         'macro':{'id':'assistant-macro-'+key,'name':label,'commands':[{'id':'assistant-script-'+key,'name':label,'type':'UserScript','path':root+'/'+key+'.js','settings':{}}]}})
    return choices
