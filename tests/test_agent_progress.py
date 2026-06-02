"""Статус agent loop в Telegram — только имена tools, без PII."""
from shared.telegram.agent_progress import format_progress_line


def test_format_progress_line_basic():
    assert format_progress_line(1, ["read_note", "search_index"]) == (
        "Шаг 1: read_note, search_index"
    )


def test_format_progress_line_truncates_many_tools():
    names = [f"tool_{i}" for i in range(10)]
    line = format_progress_line(2, names)
    assert line.startswith("Шаг 2: ")
    assert "(+4)" in line


def test_format_progress_line_empty_tools():
    assert format_progress_line(1, []) == "Шаг 1: …"
