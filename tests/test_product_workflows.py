import asyncio
import json
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from bot.db import Base
from bot.models import User, Account, Transaction
from bot.services.transaction_parse_report import parse_report
from bot.services.transaction_import import save_import, undo_import
from bot.services.import_patch import apply_patch


def test_partial_parser_preserves_good_lines_and_provenance():
    async def parse(text, **kwargs):
        if '\n' in text or text=='broken': raise ValueError('bad')
        return [{'type':'expense','amount':int(text)}]
    r=asyncio.run(parse_report(parse,'12\nbroken\n34'))
    assert [x['amount'] for x in r.transactions]==[12,34]
    assert [x['_source_line'] for x in r.transactions]==[1,3]
    assert r.issues==[{'line':2,'text':'broken','reason':'unrecognized'}]


def test_partial_parser_does_not_silently_accept_dropped_rows():
    async def parse(text, **kwargs):return [{'type':'expense','amount':1}]
    r=asyncio.run(parse_report(parse,'first\nsecond\nthird'))
    assert len(r.transactions)==3 and not r.issues


def test_patch_is_atomic_and_clears_resolution_cache():
    rows=[{'account':'A','_found_account_name':'A','amount':1},{'account':'B','amount':2}]
    result=apply_patch(rows,{'indices':[1,2],'values':{'account':'C','occurred_at':'2026-08-28'}})
    assert rows[0]['account']=='A'
    assert result[1]['account']=='C' and '_found_account_name' not in result[0]
    for patch in [{'indices':[1],'values':{'amount':'not-a-number'}}, {'indices':[0],'values':{'amount':10}}, {'indices':[1],'values':{'amount':float('nan')}}, {'indices':[1],'values':{'occurred_at':'bad'}}, {'indices':[1],'values':{'user_id':2}}]:
        with pytest.raises((ValueError,TypeError)):apply_patch(rows,patch)


def test_import_atomic_idempotent_owner_scoped_and_undo(tmp_path):
    async def scenario():
        engine=create_async_engine('sqlite+aiosqlite:///'+str(tmp_path/'test.db'))
        async with engine.begin() as conn:await conn.run_sync(Base.metadata.create_all)
        factory=async_sessionmaker(engine,expire_on_commit=False)
        async with factory() as s,s.begin():
            u=User(telegram_id=1);s.add(u);await s.flush()
            s.add(Account(user_id=u.id,name='Card',currency='USD'));uid=u.id
        row={'type':'expense','account':'Card','amount':10,'currency':'USD','category':'Food','occurred_at':'2026-08-28'}
        async with factory() as s,s.begin():a=await save_import(s,uid,'batch1',[row])
        async with factory() as s,s.begin():assert await save_import(s,uid,'batch1',[row])==a
        async with factory() as s:
            assert (await s.scalar(select(func.count()).select_from(Transaction)))==1
        with pytest.raises(ValueError):
            async with factory() as s,s.begin():await save_import(s,uid,'batch2',[dict(row,amount=20),row])
        async with factory() as s:
            assert (await s.scalar(select(func.count()).select_from(Transaction)))==1
        with pytest.raises(ValueError):
            async with factory() as s,s.begin():await undo_import(s,999,'batch1')
        async with factory() as s,s.begin():assert await undo_import(s,uid,'batch1')==1
        async with factory() as s,s.begin():assert await undo_import(s,uid,'batch1')==0
        async with factory() as s,s.begin():b=await save_import(s,uid,'batch3',[row])
        async with factory() as s,s.begin():
            txn=await s.get(Transaction,b[0]['id']);txn.amount=Decimal('11')
        with pytest.raises(ValueError):
            async with factory() as s,s.begin():await undo_import(s,uid,'batch3')
        await engine.dispose()
    asyncio.run(scenario())


def test_task_references_deadline_and_safe_undo(tmp_path,monkeypatch):
    from planning_bot.services import task_followup as follow
    from planning_bot.services import kanban_agent as ka
    from planning_bot.services.kanban import KanbanBoard
    from planning_bot.core.config import BACKLOG_COLUMN,BLOCKED_COLUMN
    monkeypatch.setenv('AGENT_ROOT',str(tmp_path));monkeypatch.setenv('KANBAN_AGENT_WRITES','1')
    monkeypatch.setattr(ka,'_sync_state_file',lambda board:None)
    path=tmp_path/'board.md';path.write_text(f'---\nkanban-plugin: board\n---\n\n## {BACKLOG_COLUMN}\n\n- [ ] Repair laptop\n\t🆔 ID: aabbccdd\n\n## {BLOCKED_COLUMN}\n')
    board=KanbanBoard(path)
    follow.remember(1,[{'task_id':'aabbccdd','title':'Repair laptop'}])
    assert follow.resolve_position(1,1)=='aabbccdd'
    with pytest.raises(ValueError):follow.resolve_position(2,1)
    r=json.loads(follow.mutate(board,1,action='reschedule',task_id='aabbccdd',deadline='2026-08-28'))
    assert r['status']=='ok' and r['deadline']=='2026-08-28'
    assert json.loads(follow.mutate(board,1,action='undo'))['status']=='ok'
    assert '2026-08-28' not in path.read_text()
    follow.mutate(board,1,action='move',task_id='aabbccdd',column=BLOCKED_COLUMN)
    path.write_text(path.read_text().replace('Repair laptop','Changed title'))
    assert json.loads(follow.mutate(board,1,action='undo'))['status']=='conflict'


def test_status_never_claims_old_report_is_fresh(tmp_path,monkeypatch):
    from shared.agent import data_status as ds
    monkeypatch.setenv('VAULT_PATH',str(tmp_path));monkeypatch.setattr(ds,'get_capabilities',lambda:SimpleNamespace(connector=lambda x:x=='apple_health'))
    (tmp_path/'.sync').mkdir()
    (tmp_path/'.sync/pipeline_health.json').write_text(json.dumps({'status':'ok','checked_at':'2000-01-01T00:00:00+00:00','sources':{'iphone':{'status':'ok'},'broker':{'status':'ok'}}}))
    result=ds.read_status();assert result['status']=='unknown' and set(result['sources'])=={'iphone'}


def test_completion_undo_is_not_counted_and_can_complete_again():
    from planning_bot.services.action_log_parser import get_completion_events
    events=[{'type':'task_completed','dt':datetime(2026,1,1),'data':{'task_id':'a','title':'A'}},
            {'type':'task_reopened','dt':datetime(2026,1,2),'data':{'task_id':'a'}},
            {'type':'task_completed','dt':datetime(2026,1,3),'data':{'task_id':'b','title':'B'}}]
    assert [e['data']['task_id'] for e in get_completion_events(events,filter_batch=False)]==['b']
    events.append({'type':'task_completed','dt':datetime(2026,1,4),'data':{'task_id':'a','title':'A'}})
    assert [e['data']['task_id'] for e in get_completion_events(events,filter_batch=False)]==['b','a']


def test_review_router_imports_and_patch_catalogs():
    import yaml
    from bot.handlers.transactions_confirm import router
    from planning_bot.app.task_tools import apply_kanban_task
    assert router and 'position' in apply_kanban_task._agent_tool_meta['parameters']['properties']
    for locale in ('en','ru'):
        data=yaml.safe_load((Path(__file__).resolve().parents[1]/f'config/messages.{locale}.yaml.example').read_text())
        assert data['finance']['import_summary'] and data['host']['data_status_button']


def test_mail_archive_targets_uid_and_never_deletes():
    from planning_bot.services.health_mail_archive import message_uid,archive_accepted
    calls=[]
    client=SimpleNamespace(uid=lambda *args:(calls.append(args) or ('OK',[])))
    uid=message_uid(b'12 (UID 991 BODY[] {12})')
    archive_accepted(client,uid)
    assert calls==[('STORE',b'991','-X-GM-LABELS',r'(\Inbox)')]
    with pytest.raises(ValueError):archive_accepted(client,None)


def test_batch_routes_invalid_row_to_review_instead_of_aborting(monkeypatch):
    from bot.handlers.transactions import nlu, import_review
    from bot.handlers import badge
    from bot.services.transaction_parse_report import ParseReport
    report=ParseReport(transactions=[{'type':'expense','amount':10},{'type':'expense','amount':'invalid'}],total_lines=2)
    monkeypatch.setattr(nlu,'TransactionNLUParser',lambda:SimpleNamespace(parse_report=AsyncMock(return_value=report)))
    monkeypatch.setattr(badge,'infer_badge_spend_text',lambda text:False)
    monkeypatch.setattr(badge,'parsed_expenses_are_badge',lambda rows:False)
    check=AsyncMock(side_effect=ValueError('invalid amount'));monkeypatch.setattr(nlu,'get_missing_fields',check)
    review=AsyncMock();monkeypatch.setattr(import_review,'review',review)
    message=SimpleNamespace(from_user=SimpleNamespace(id=1),answer=AsyncMock(return_value=SimpleNamespace(delete=AsyncMock())))
    state=SimpleNamespace(get_data=AsyncMock(return_value={}),get_state=AsyncMock(return_value=None),update_data=AsyncMock(),set_state=AsyncMock())
    asyncio.run(nlu.process_transactions('first\nsecond',message,state))
    check.assert_not_awaited();review.assert_awaited_once()
    assert any(call.kwargs.get('transactions')==report.transactions for call in state.update_data.call_args_list)
