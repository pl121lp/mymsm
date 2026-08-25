from datetime import date
from decimal import Decimal

from amortization import (
    AmortizationInputs,
    compute_future_amortization,
    infer_payments_per_year,
)


def test_infer_payments_per_year_detects_monthly_cadence():
    dates = [date(2024, 1, 15), date(2024, 2, 15), date(2024, 3, 15), date(2024, 4, 15)]
    assert infer_payments_per_year(dates) == 12


def test_infer_payments_per_year_detects_quarterly_cadence():
    dates = [date(2024, 1, 1), date(2024, 4, 2), date(2024, 7, 1), date(2024, 10, 1)]
    assert infer_payments_per_year(dates) == 4


def test_infer_payments_per_year_detects_annual_cadence():
    dates = [date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1)]
    assert infer_payments_per_year(dates) == 1


def test_infer_payments_per_year_defaults_to_monthly_with_fewer_than_two_dates():
    assert infer_payments_per_year([]) == 12
    assert infer_payments_per_year([date(2024, 1, 1)]) == 12


def test_compute_future_amortization_projects_to_payoff():
    inputs = AmortizationInputs(
        current_balance=Decimal("-1000"),
        annual_rate=Decimal("0.10"),
        payment_amount=Decimal("600"),
        payments_per_year=1,
        start_date=date(2024, 1, 1),
    )
    points = compute_future_amortization(inputs)
    assert points == [
        (date(2025, 1, 1), Decimal("-500")),
        (date(2026, 1, 1), Decimal("0")),
    ]


def test_compute_future_amortization_returns_none_when_payment_does_not_cover_interest():
    inputs = AmortizationInputs(
        current_balance=Decimal("-1000"),
        annual_rate=Decimal("0.24"),
        payment_amount=Decimal("10"),
        payments_per_year=12,
        start_date=date(2024, 1, 1),
    )
    assert compute_future_amortization(inputs) is None


def test_compute_future_amortization_returns_none_when_max_periods_exceeded():
    inputs = AmortizationInputs(
        current_balance=Decimal("-100000"),
        annual_rate=Decimal("0.12"),
        payment_amount=Decimal("1001"),
        payments_per_year=12,
        start_date=date(2024, 1, 1),
    )
    assert compute_future_amortization(inputs, max_periods=5) is None


def test_compute_future_amortization_returns_empty_list_when_already_paid_off():
    inputs = AmortizationInputs(
        current_balance=Decimal("0"),
        annual_rate=Decimal("0.05"),
        payment_amount=Decimal("100"),
        payments_per_year=12,
        start_date=date(2024, 1, 1),
    )
    assert compute_future_amortization(inputs) == []
