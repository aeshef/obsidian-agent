import ast
from pathlib import Path

import pytest
import yaml

from planning_bot.services import kanban_agent as ka
from planning_bot.services.kanban import KanbanBoard
from planning_bot.core.config import BACKLOG_COLUMN, BLOCKED_COLUMN


@pytest.mark.parametrize('locale', ['en', 'ru'])
def test_all_kanban_result_messages_exist(locale):
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root / 'planning_bot/services/kanban_agent.py').read_text())
    keys = {n.args[0].value for n in ast.walk(tree)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == 'pdmsg' and n.args and isinstance(n.args[0], ast.Constant)}
    catalog = yaml.safe_load((root / f'config/domain_messages/{locale}/planning.yaml.example').read_text())['planning']
    assert all(catalog.get(key) for key in keys), keys - catalog.keys()


def test_typo_suggests_id_without_moving_then_exact_id_succeeds(tmp_path, monkeypatch):
    monkeypatch.setenv('KANBAN_AGENT_WRITES', '1')
    monkeypatch.setattr(ka, '_sync_state_file', lambda board: None)
    path = tmp_path / 'board.md'
    original = f'---\nkanban-plugin: board\n---\n\n## {BACKLOG_COLUMN}\n\n- [ ] Repair lpatop at service center\n\t🆔 ID: aabbccdd\n\n## {BLOCKED_COLUMN}\n'
    path.write_text(original)
    board = KanbanBoard(path)
    response = ka.apply_kanban_action(board, action='move', title='Repair laptop', column=BLOCKED_COLUMN)
    assert response.strip()
    assert 'aabbccdd' in response and 'Repair lpatop at service center' in response
    assert path.read_text() == original
    result = ka.apply_kanban_action(board, action='move', task_id='aabbccdd', column=BLOCKED_COLUMN)
    assert result.startswith('OK:')
    assert ka._find_task_block(ka._parse_sections(path.read_text()), 'aabbccdd')[0] == BLOCKED_COLUMN


def test_failed_lookup_and_unknown_column_have_explanations(tmp_path, monkeypatch):
    monkeypatch.setenv('KANBAN_AGENT_WRITES', '1')
    path = tmp_path / 'board.md'
    original = f'## {BACKLOG_COLUMN}\n\n- [ ] Repair laptop\n\t🆔 ID: aabbccdd\n'
    path.write_text(original)
    board = KanbanBoard(path)
    for args in [dict(action='move', title='Unrelated request', column=BLOCKED_COLUMN),
                 dict(action='move', task_id='aabbccdd', column='Unknown column'),
                 dict(action='invalid')]:
        assert ka.apply_kanban_action(board, **args).strip()
        assert path.read_text() == original
