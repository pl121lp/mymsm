"""Loan amortization: infers real payment cadence from a loan's own
transaction history (never Money's undocumented `frq` field) and
projects a standard declining-balance schedule forward from the most
recent known balance to payoff.
"""

import calendar
import statistics
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import NamedTuple, Optional

_FREQUENCY_CANDIDATES = [(12, 30.44), (4, 91.31), (2, 182.63), (1, 365.25)]


def infer_payments_per_year(dates: list[date]) -> int:
    """Snaps the median gap between sorted dates to the nearest of
    {12, 4, 2, 1} (monthly/quarterly/semi-annual/annual) payments per
    year. Defaults to 12 (monthly) with fewer than two dates -- matches
    the overwhelming majority of real loan accounts and is a safe
    default for a loan with no payment history yet."""
    ordered = sorted(dates)
    if len(ordered) < 2:
        return 12
    gaps = [(later - earlier).days for earlier, later in zip(ordered, ordered[1:])]
    median_gap = statistics.median(gaps)
    return min(_FREQUENCY_CANDIDATES, key=lambda candidate: abs(median_gap - candidate[1]))[0]


def _add_months(base_date: date, months: int) -> date:
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return base_date.replace(year=year, month=month, day=day)


@dataclass
class AmortizationInputs:
    current_balance: Decimal  # liability convention: negative = owed
    annual_rate: Decimal      # fraction, e.g. Decimal("0.05") for 5%
    payment_amount: Decimal   # positive, principal + interest only
    payments_per_year: int
    start_date: date          # date of current_balance


class AmortizationPoint(NamedTuple):
    point_date: date
    balance: Decimal


def compute_future_amortization(
    inputs: AmortizationInputs, max_periods: int = 1200
) -> Optional[list[AmortizationPoint]]:
    """Standard declining-balance amortization, one point per period,
    stepping forward from inputs.start_date. Each period: interest =
    -balance * (annual_rate / payments_per_year); principal_paid =
    payment_amount - interest; balance += principal_paid. The final
    balance is clamped to exactly 0. Returns [] immediately if the loan
    is already paid off (current_balance >= 0). Returns None if
    principal_paid is never positive (the payment doesn't cover the
    period's interest) or payoff isn't reached within max_periods -- the
    loan doesn't amortize under its recorded terms.

    Dates step by 12 // payments_per_year calendar months, so monthly,
    quarterly, semi-annual, and annual periods all land on sensible
    calendar dates (same day-of-month clamping as models.py's
    _add_months, duplicated here to keep this module dependency-free).
    """
    if inputs.current_balance >= 0:
        return []

    periodic_rate = inputs.annual_rate / inputs.payments_per_year
    months_per_period = 12 // inputs.payments_per_year
    balance = inputs.current_balance
    point_date = inputs.start_date
    points = []

    for _ in range(max_periods):
        interest = -balance * periodic_rate
        principal_paid = inputs.payment_amount - interest
        if principal_paid <= 0:
            return None
        point_date = _add_months(point_date, months_per_period)
        balance += principal_paid
        if balance >= 0:
            points.append(AmortizationPoint(point_date, Decimal("0")))
            return points
        points.append(AmortizationPoint(point_date, balance))

    return None
