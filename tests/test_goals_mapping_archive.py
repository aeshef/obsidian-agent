from __future__ import annotations


def test_missing_goals_selection_includes_completed_archive_tasks():
    from planning_bot.tools.map_missing_goals import select_missing_tasks

    tasks = [
        {"task_id": "active1", "completed": False, "source": "active"},
        {"task_id": "done1", "completed": True, "source": "active"},
        {"task_id": "arch1", "completed": True, "source": "archive"},
        {"title": "no id", "completed": True, "source": "archive"},
    ]

    missing = select_missing_tasks(tasks, {"active1": ["goal"]})

    assert [t["task_id"] for t in missing] == ["done1", "arch1"]


def test_goal_progress_counts_completed_field(monkeypatch):
    from planning_bot.core.config import BACKLOG_COLUMN
    from planning_bot.services.goals_analyzer import GoalsAnalyzer

    analyzer = object.__new__(GoalsAnalyzer)
    analyzer.mapper = type(
        "Mapper",
        (),
        {
            "goals": {"g1": {"text": "Goal"}},
            "get_tasks_for_goal": lambda self, goal_id: ["done1", "todo1"],
        },
    )()
    analyzer.kanban = type(
        "Kanban",
        (),
        {
            "load": lambda self: None,
            "get_tasks": lambda self, exclude_today=False: [
                {"task_id": "done1", "completed": True, "column": "Archive"},
                {"task_id": "todo1", "completed": False, "column": BACKLOG_COLUMN},
            ],
        },
    )()

    progress = analyzer.get_goal_progress("g1")

    assert progress["total_tasks"] == 2
    assert progress["completed"] == 1
    assert progress["backlog"] == 1


def test_no_goal_mapping_is_recorded_as_reviewed():
    from planning_bot.tools.map_missing_goals import record_no_goal_mapping

    calls = []
    mapper = type(
        "Mapper",
        (),
        {
            "mapping": {},
            "save_mapping": lambda self, task_info=None: calls.append(task_info),
        },
    )()

    record_no_goal_mapping(mapper, "task1", "Task title")

    assert mapper.mapping == {"task1": []}
    assert calls == [{"task1": "Task title"}]
