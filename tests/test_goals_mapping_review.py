from __future__ import annotations

from shared.goals.mapping_review import (
    build_review_data,
    collect_multi_goal_tasks,
    collect_orphan_goal_refs,
    format_quarter_label,
    render_goals_mapping_review,
    sanitize_inline,
)


def test_format_quarter_label_avoids_double_q():
    assert format_quarter_label("Q2") == "Q2"
    assert format_quarter_label("2") == "Q2"
    assert format_quarter_label("") == ""


def test_sanitize_inline_strips_newlines():
    assert sanitize_inline("line1\nline2") == "line1 line2"
    assert sanitize_inline("a" * 200).endswith("…")


def test_collect_orphan_goal_refs():
    goals = {"alive": {"text": "Keep"}}
    readable = {
        "t1": {"goals": [{"id": "dead", "text": "Old goal"}, {"id": "alive", "text": "Keep"}]},
        "t2": {"goals": [{"id": "dead", "text": "Old goal"}]},
    }
    orphans = collect_orphan_goal_refs(goals, readable)
    assert orphans == [{"id": "dead", "text": "Old goal"}]


def test_collect_multi_goal_tasks():
    mapping = {"t1": ["g1", "g2", "g3"], "t2": ["g1", "g2"]}
    tasks = {"t1": {"title": "Wide", "completed": False}}
    multi = collect_multi_goal_tasks(mapping, tasks, {}, min_goals=3)
    assert len(multi) == 1
    assert multi[0]["task_id"] == "t1"
    assert multi[0]["goal_count"] == 3


def test_build_review_data_groups_tasks_by_goal():
    goals = {
        "g1": {
            "text": "Goal one",
            "quarter": "Q2",
            "priority": "high",
            "category": "work",
            "context": "Meaning",
            "include": "Direct steps",
            "exclude": "Adjacent work",
            "success": "Done",
        },
        "g2": {"text": "Goal two", "quarter": "Q2", "priority": "", "category": ""},
    }
    mapping = {"t1": ["g1"], "t2": ["g1", "g2"], "t3": []}
    tasks_by_id = {
        "t1": {"title": "Task A", "completed": True, "column": "Done", "source": "active"},
        "t2": {"title": "Task B", "completed": False, "column": "Backlog", "source": "active"},
        "t4": {"title": "Unmapped", "completed": False, "column": "Backlog", "source": "active"},
    }
    data = build_review_data(goals, mapping, tasks_by_id, {})
    assert data["summary"]["active_goals"] == 2
    assert data["summary"]["unmapped_board_tasks"] == 1
    assert len(data["goals"]) == 2
    g1 = next(g for g in data["goals"] if g["id"] == "g1")
    assert len(g1["tasks"]) == 2
    assert g1["done_count"] == 1
    assert g1["context"] == "Meaning"
    assert g1["include"] == "Direct steps"
    assert g1["exclude"] == "Adjacent work"
    assert g1["success"] == "Done"
    assert data["unmapped_open"][0]["task_id"] == "t4"


def test_goals_mapper_parses_indented_goal_context_fields():
    from planning_bot.services.goals_mapper import GoalsMapper

    mapper = object.__new__(GoalsMapper)
    mapper.goals = {}
    content = """
## Q3 2026
- [ ] Build outcome #цель/развитие #приоритет/высокий #фокус/Q3
  context:: what this goal means
  include:: direct steps
  exclude:: adjacent but wrong
  success:: visible completion
- [ ] Other outcome #цель/дом
"""
    mapper._parse_goals_from_content(content, type("P", (), {"name": "goals.md"})())
    goal = next(g for g in mapper.goals.values() if g["text"] == "Build outcome")
    assert goal["context"] == "what this goal means"
    assert goal["include"] == "direct steps"
    assert goal["exclude"] == "adjacent but wrong"
    assert goal["success"] == "visible completion"


def test_goals_mapper_ignores_goal_examples_inside_code_fences():
    from planning_bot.services.goals_mapper import GoalsMapper

    mapper = object.__new__(GoalsMapper)
    mapper.goals = {}
    content = """
- [ ] Real goal #цель/развитие
```markdown
- [ ] Example goal #цель/дом
```
"""
    mapper._parse_goals_from_content(content, type("P", (), {"name": "goals.md"})())
    assert [g["text"] for g in mapper.goals.values()] == ["Real goal"]


def test_goals_mapper_parses_context_fields_from_obsidian_callout():
    from planning_bot.services.goals_mapper import GoalsMapper

    mapper = object.__new__(GoalsMapper)
    mapper.goals = {}
    content = """
- [ ] Callout goal #цель/развитие
  > [!info]- Контекст маппинга
  > context:: meaning
  > include:: direct steps
  > exclude:: adjacent
  > success:: done
"""
    mapper._parse_goals_from_content(content, type("P", (), {"name": "goals.md"})())
    goal = next(iter(mapper.goals.values()))
    assert goal["context"] == "meaning"
    assert goal["include"] == "direct steps"
    assert goal["exclude"] == "adjacent"
    assert goal["success"] == "done"


def test_goals_mapper_parses_russian_context_aliases():
    from planning_bot.services.goals_mapper import GoalsMapper

    mapper = object.__new__(GoalsMapper)
    mapper.goals = {}
    content = """
- [ ] RU goal #цель/развитие
  контекст:: смысл цели
  включать:: прямые шаги
  исключать:: соседнее
  успех:: готово
"""
    mapper._parse_goals_from_content(content, type("P", (), {"name": "goals.md"})())
    goal = next(iter(mapper.goals.values()))
    assert goal["context"] == "смысл цели"
    assert goal["include"] == "прямые шаги"
    assert goal["exclude"] == "соседнее"
    assert goal["success"] == "готово"


def test_scaffold_goal_contexts_adds_callouts_idempotently():
    from planning_bot.scripts.scaffold_goal_contexts import scaffold_goal_contexts

    text = """- [ ] Real goal #цель/развитие
```markdown
- [ ] Example goal #цель/дом
```
"""
    updated, inserted = scaffold_goal_contexts(text)
    assert inserted == 1
    assert "> [!info]- Контекст маппинга" in updated

    updated_again, inserted_again = scaffold_goal_contexts(updated)
    assert inserted_again == 0
    assert updated_again == updated


def test_render_uses_obsidian_callouts():
    data = build_review_data(
        {"g1": {"text": "G", "quarter": "Q1", "priority": "", "category": ""}},
        {"t1": ["g1"]},
        {"t1": {"title": "T", "completed": False, "column": "X", "source": "active"}},
        {},
    )
    md = render_goals_mapping_review(data, lambda k: k, {})
    assert "[!abstract]" in md
    assert "`g1`" in md
    assert "`t1`" in md
    assert "<details>" not in md


def test_render_suspicious_section_for_multi_goal_task():
    goals = {f"g{i}": {"text": f"G{i}"} for i in range(4)}
    mapping = {"t1": ["g0", "g1", "g2"]}
    data = build_review_data(goals, mapping, {"t1": {"title": "X", "completed": False}}, {})
    md = render_goals_mapping_review(data, lambda k: k, {})
    assert "goals_mapping_review_suspicious_heading" in md
    assert "`t1`" in md


def test_reconcile_mapping_drops_orphan_goal_ids():
    from planning_bot.services.goals_mapper import GoalsMapper

    mapper = object.__new__(GoalsMapper)
    mapper.goals = {"g1": {"text": "Alive"}}
    mapper.mapping = {"t1": ["g1", "gone"], "t2": ["gone"]}
    mapper.mapping_file = type("P", (), {"parent": type("PP", (), {"mkdir": lambda *a, **k: None})()})()
    mapper.task_titles = {}
    saved = []

    def _save(self, task_info=None):
        saved.append(True)

    mapper.save_mapping = lambda task_info=None: _save(mapper, task_info)

    stats = mapper.reconcile_mapping(persist=True, remove_ghost_tasks=False)
    assert mapper.mapping == {"t1": ["g1"]}
    assert stats["orphan_goal_refs"] == 2
    assert stats["empty_mappings_removed"] == 1
    assert saved == [True]
