import pytest
from shared.obsidian_ui import layout
from unified_bot.integrations import dashboard_datasets as datasets


def setup(monkeypatch,tmp_path):
    (tmp_path/'ui').mkdir()
    monkeypatch.setattr(layout,'install_assets',lambda v:'ui')
    monkeypatch.setattr(datasets,'export_dataset',lambda *a:None)


@pytest.mark.parametrize("kind", ["analytics", "health", "finance", "calendar"])
def test_chart_stays_in_its_section(tmp_path,monkeypatch,kind):
    setup(monkeypatch,tmp_path)
    body='# Analytics\n\n## Body\n\n### Weight\n\n![[300_Дашборды/Графики/weight.png]]\n'
    result=layout.present_dashboard(body,tmp_path,kind)
    if kind == "health":
        assert '![[300_Дашборды/Графики/weight.png]]' not in result
        assert 'kind: "health"' in result
    else:
        assert '![[300_Дашборды/Графики/weight.png]]' in result
    assert 'Дополнительные отчёты и экспорт' not in result


def test_progress_has_no_export_appendix(tmp_path,monkeypatch):
    setup(monkeypatch,tmp_path)
    from shared.obsidian_ui import reports
    monkeypatch.setattr(reports,'folder',lambda k:'dash')
    monkeypatch.setattr(reports,'dashboards_sub',lambda k:'charts')
    result=layout.present_dashboard('# Progress\n\n## Goals\nContent\n\n### Old report\n![[dash/charts/old.png]]',tmp_path,'progress')
    assert 'Content' in result and 'old.png' not in result and 'Old report' not in result
