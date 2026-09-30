"""Owner-scoped references to the last displayed list and safe single-task undo."""
import json
import os
import time
import re
from pathlib import Path
from datetime import date
from uuid import uuid4
from planning_bot.services import kanban_parse as kp
from planning_bot.services.kanban_lock import kanban_transaction
from shared.agent.platform_config import platform_int


def _path(user_id):
    return Path(os.environ.get("AGENT_ROOT", "."))/"logs"/"task_followup"/(str(int(user_id))+".json")


def load(user_id):
    try:
        data=json.loads(_path(user_id).read_text())
        if time.time()-data.get("updated",0)>platform_int("task_followup","ttl_seconds",default=86400): return {}
        return data
    except (OSError,ValueError): return {}


def save(user_id, data):
    p=_path(user_id);p.parent.mkdir(parents=True,exist_ok=True)
    temp=p.with_suffix('.'+uuid4().hex+'.tmp');temp.write_text(json.dumps(dict(data,updated=time.time()),ensure_ascii=False));temp.replace(p)


def remember(user_id, tasks):
    data=load(user_id);data['list']=[{'position':i+1,'task_id':t.get('task_id'),'title':t.get('title')} for i,t in enumerate(tasks)]
    save(user_id,data)


def resolve_position(user_id, position):
    tasks=load(user_id).get('list',[])
    if position<1 or position>len(tasks) or not tasks[position-1].get('task_id'):
        raise ValueError('reference_expired_or_unknown; request a fresh task list')
    return tasks[position-1]['task_id']


def mutate(board, user_id, *, action, task_id='', title='', column='', deadline='', dry_run=False, logger=None):
    from planning_bot.services.kanban_agent import (kanban_writes_allowed,resolve_task_ids,resolve_column_name,
                _rebuild_kanban_content,_sync_state_file)
    from planning_bot.core.config import DONE_COLUMN
    if not kanban_writes_allowed() and not dry_run: return json.dumps({'status':'writes_disabled'})
    data=load(user_id)
    with kanban_transaction(board.file_path):
        board.load();sections=kp.parse_sections(board.content)
        if action=='undo':
            undo=data.get('undo')
            if not undo:return json.dumps({'status':'nothing_to_undo'})
            task_id=undo['task_id'];found=kp.find_task_block(sections,task_id)
            if not found or [found[0],found[2]]!=undo['after']:return json.dumps({'status':'conflict','reason':'task_changed_since_action'})
            src,index,block=found; target,new_block=undo['before']
        else:
            ids,note=resolve_task_ids(sections,task_id=task_id,title=title,all_matching=False)
            if len(ids)!=1:return json.dumps({'status':'needs_choice','candidates':note},ensure_ascii=False)
            task_id=ids[0];src,index,block=kp.find_task_block(sections,task_id)
            target=src;new_block=block
            if action=='complete': target=DONE_COLUMN;new_block=re.sub(r'- \[ \]','- [x]',block,count=1)
            elif action=='move':
                target=resolve_column_name(column)
                if not target:return json.dumps({'status':'unknown_column'})
            elif action=='reschedule':
                date.fromisoformat(deadline)
                from planning_bot.services.kanban_format import tag_deadline_regex
                from planning_bot.core.config import _kanban_schema
                prefix=(_kanban_schema().get('tag_prefixes') or {}).get('deadline','deadline')
                tag='#'+prefix+'/'+deadline
                pattern=tag_deadline_regex()
                if pattern.search(block):new_block=pattern.sub(tag,block)
                else:
                    lines=block.splitlines();lines[0]+=' '+tag;new_block='\n'.join(lines)
            else:raise ValueError('unsupported_action')
        if dry_run:return json.dumps({'status':'preview','task_id':task_id,'from':src,'to':target,'deadline':deadline},ensure_ascii=False)
        sections[src].pop(index);sections.setdefault(target,[]).append(new_block)
        board.content=_rebuild_kanban_content(sections,board.content);board.save()
        data['undo']=None if action=='undo' else {'task_id':task_id,'before':[src,block],'after':[target,new_block]}
        save(user_id,data)
    _sync_state_file(board)
    if logger:
        name=kp.title_from_block(new_block)
        if action=='complete':logger.log_task_completed(name,task_id=task_id)
        elif action=='undo' and re.search(r'- \[x\]',block) and re.search(r'- \[ \]',new_block):
            logger.log_action('task_reopened',{'title':name,'task_id':task_id,'from':src,'to':target})
        elif action=='reschedule':
            logger.log_action('task_rescheduled',{'title':name,'task_id':task_id,'deadline':deadline})
        elif src!=target:logger.log_task_moved(name,src,target,task_id=task_id)
    return json.dumps({'status':'ok','action':action,'task_id':task_id,'column':target,'deadline':kp.metadata_from_block(new_block).get('deadline')},ensure_ascii=False)
