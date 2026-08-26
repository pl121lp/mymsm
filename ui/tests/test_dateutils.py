from datetime import date

from dateutils import add_months


def test_add_months_advances_month_and_keeps_day():
    assert add_months(date(2024, 1, 10), 3) == date(2024, 4, 10)


def test_add_months_rolls_over_year_boundary():
    assert add_months(date(2024, 11, 20), 3) == date(2025, 2, 20)


def test_add_months_clamps_to_shorter_month_end():
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)


def test_add_months_zero_returns_same_date():
    assert add_months(date(2024, 5, 15), 0) == date(2024, 5, 15)
