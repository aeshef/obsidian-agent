from datetime import date

from shared.parsing.date_range import resolve_date_range


def test_resolve_from_to():
    dr = resolve_date_range(
        from_date="2026-05-01",
        to_date="2026-05-10",
        anchor=date(2026, 5, 15),
    )
    assert dr.start == date(2026, 5, 1)
    assert dr.end == date(2026, 5, 10)


def test_resolve_days():
    dr = resolve_date_range(days=7, anchor=date(2026, 5, 10))
    assert dr.end == date(2026, 5, 10)
    assert dr.start == date(2026, 5, 4)
