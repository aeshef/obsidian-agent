import json

from planning_bot.scripts import build_task_completions_index as module


def test_explicit_vault_controls_source_and_output(tmp_path, monkeypatch):
    seen = []
    monkeypatch.setattr(module, 'collect_events_from_logs', lambda path: seen.append(path) or [])
    out = module.build_task_completions_index(vault=tmp_path)
    assert seen == [tmp_path / module.folder('dashboards') / module.dashboards_sub('logs')]
    assert out.is_relative_to(tmp_path)
    assert json.loads(out.read_text())['completions'] == {}


def test_default_vault_is_parent_of_dashboard_directory(tmp_path, monkeypatch):
    monkeypatch.setattr(module, 'LOGS_DIR', tmp_path / module.folder('dashboards'))
    monkeypatch.setattr(module, 'collect_events_from_logs', lambda path: [])
    assert module.build_task_completions_index().is_relative_to(tmp_path)
