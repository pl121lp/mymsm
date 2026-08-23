"""Forward-looking net worth projection, driven by user-entered
assumptions rather than real transaction data (contrast with
models.compute_net_worth_series, which is historical).
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import NamedTuple, Optional


@dataclass
class ProjectionInputs:
    birth_year: int
    end_year: int
    retirement_age: int
    starting_investment_value: Decimal
    return_rate_before_retirement: Decimal
    return_rate_after_retirement: Decimal
    annual_income: Decimal
    tax_rate: Decimal
    inflation_rate: Decimal
    spending_before_retirement: Decimal
    spending_after_retirement: Decimal
    social_security_annual_amount: Decimal
    social_security_start_year: int


class YearlyProjection(NamedTuple):
    year: int
    age: int
    retired: bool
    income: Decimal
    social_security: Decimal
    tax: Decimal
    spending: Decimal
    net_cash_flow: Decimal
    investment_value: Decimal
    net_worth: Decimal


def compute_projection(
    inputs: ProjectionInputs, current_year: Optional[int] = None
) -> list[YearlyProjection]:
    """Year-by-year projection from current_year through inputs.end_year.

    Year 0 (current_year) is a snapshot at starting_investment_value with
    no cash flow or growth applied yet. Each later year escalates income,
    Social Security, and spending by inflation_rate, stops income (but not
    Social Security) once retired, applies tax_rate to income + Social
    Security only, and compounds both investment_value (market growth
    alone) and net_worth (market growth plus that year's net cash flow) at
    the before/after-retirement return rate. net_worth is never floored at
    zero -- a shortfall keeps compounding as a negative balance.
    """
    if current_year is None:
        current_year = date.today().year

    retirement_year = inputs.birth_year + inputs.retirement_age
    zero = Decimal("0")
    one = Decimal("1")

    rows = [
        YearlyProjection(
            year=current_year,
            age=current_year - inputs.birth_year,
            retired=current_year >= retirement_year,
            income=zero,
            social_security=zero,
            tax=zero,
            spending=zero,
            net_cash_flow=zero,
            investment_value=inputs.starting_investment_value,
            net_worth=inputs.starting_investment_value,
        )
    ]

    for year in range(current_year + 1, inputs.end_year + 1):
        prior = rows[-1]
        years_elapsed = year - current_year
        retired = year >= retirement_year
        inflation_factor = (one + inputs.inflation_rate) ** years_elapsed

        income = zero if retired else inputs.annual_income * inflation_factor
        social_security = (
            inputs.social_security_annual_amount * inflation_factor
            if year >= inputs.social_security_start_year
            else zero
        )
        spending = (
            inputs.spending_after_retirement if retired else inputs.spending_before_retirement
        ) * inflation_factor
        tax = (income + social_security) * inputs.tax_rate
        net_cash_flow = income + social_security - tax - spending

        return_rate = (
            inputs.return_rate_after_retirement if retired else inputs.return_rate_before_retirement
        )
        investment_value = prior.investment_value * (one + return_rate)
        net_worth = (prior.net_worth + net_cash_flow) * (one + return_rate)

        rows.append(
            YearlyProjection(
                year=year,
                age=year - inputs.birth_year,
                retired=retired,
                income=income,
                social_security=social_security,
                tax=tax,
                spending=spending,
                net_cash_flow=net_cash_flow,
                investment_value=investment_value,
                net_worth=net_worth,
            )
        )

    return rows
