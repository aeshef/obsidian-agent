from planning_bot.services.kanban_agent import filter_tasks, kanban_writes_allowed


def test_filter_tasks_column_and_priority():
    tasks = [
        {
            "title": "Deploy",
            "column": "🔄 В работе",
            "category": "работа",
            "priority": "высокий",
            "deadline": "2026-06-01",
            "completed": False,
            "task_id": "abc",
        },
        {
            "title": "Buy milk",
            "column": "📋 Бэклог",
            "category": "личное",
            "priority": "низкий",
            "deadline": None,
            "completed": False,
            "task_id": "def",
        },
    ]
    out = filter_tasks(tasks, column="работе", priority="высок")
    assert len(out) == 1
    assert out[0]["task_id"] == "abc"


def test_kanban_writes_default_off():
    assert kanban_writes_allowed() is False
