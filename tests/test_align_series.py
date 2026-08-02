"""Day-series alignment helper."""
from __future__ import annotations

from shared.query.align_series import align_two_texts, parse_day_values


def test_parse_and_align():
    a = "2026-04-01|10\n2026-04-02|20\n"
    b = "2026-04-02\t5\n2026-04-03|7\n"
    assert parse_day_values(a)["2026-04-01"] == 10
    _series, body = align_two_texts(a, b, label_a="spend", label_b="tasks", fill_zero=True)
    assert "2026-04-01" in body
    assert "2026-04-03" in body
    assert "shared=1" in body
