"""Forward-looking net worth projection, driven by user-entered
assumptions rather than real transaction data (contrast with
models.compute_net_worth_series, which is historical).
"""

from dataclasses import dataclass, field
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
    social_security_annual_amount_2: Decimal
    social_security_start_year_2: int
    house_sale_value: Decimal
    house_sale_year: int
    inheritance_amount: Decimal
    inheritance_year: int
    medical_cost_after_retirement: Decimal
    medicare_age: int
    withdrawal_tax_rate: Decimal
    extra_annual_cash_flows: dict[int, Decimal] = field(default_factory=dict)


class YearlyProjection(NamedTuple):
    year: int
    age: int
    retired: bool
    income: Decimal
    social_security: Decimal
    tax: Decimal
    spending: Decimal
    net_cash_flow: Decimal
    net_worth: Decimal


def compute_projection(
    inputs: ProjectionInputs, current_year: Optional[int] = None
) -> list[YearlyProjection]:
    """Year-by-year projection from current_year through inputs.end_year.

    Year 0 (current_year) is a snapshot at starting_investment_value with
    no cash flow or growth applied yet. Each later year escalates income,
    Social Security, and spending by inflation_rate, stops income (but not
    Social Security) once retired, applies tax_rate to income + Social
    Security only, and compounds net_worth (a single pool -- there is no
    separate untouched "investment value") at the before/after-retirement
    return rate on top of that year's net cash flow. net_worth is never
    floored at zero -- a shortfall keeps compounding as a negative balance.

    Social Security supports two independent people/benefits, each with
    its own inflation-adjusted amount and start year; the two are summed
    into a single social_security total for tax and cash flow purposes.

    Medical costs (medical_cost_after_retirement, inflation-adjusted) are
    added to retirement spending only while age < medicare_age.

    In retired years where income + Social Security (after tax) doesn't
    cover spending, the shortfall is funded by selling investments, and
    that sale is itself taxed: the amount actually withdrawn is grossed up
    by withdrawal_tax_rate so the after-tax proceeds cover the shortfall.
    This does not apply before retirement, and does not apply to house-sale
    or inheritance lump sums, which are added in full in their given year.

    extra_annual_cash_flows optionally maps a year to an additional cash
    flow added to that year's net_cash_flow before compounding -- callers
    use this to fold in e.g. RSU vesting proceeds or a college-tuition
    fund's contributions/withdrawals without this module needing to know
    about either.
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
            net_worth=inputs.starting_investment_value,
        )
    ]

    for year in range(current_year + 1, inputs.end_year + 1):
        prior = rows[-1]
        years_elapsed = year - current_year
        age = year - inputs.birth_year
        retired = year >= retirement_year
        inflation_factor = (one + inputs.inflation_rate) ** years_elapsed

        income = zero if retired else inputs.annual_income * inflation_factor
        social_security = (
            inputs.social_security_annual_amount * inflation_factor
            if year >= inputs.social_security_start_year
            else zero
        ) + (
            inputs.social_security_annual_amount_2 * inflation_factor
            if year >= inputs.social_security_start_year_2
            else zero
        )
        medical = (
            inputs.medical_cost_after_retirement * inflation_factor
            if retired and age < inputs.medicare_age
            else zero
        )
        spending = (
            inputs.spending_after_retirement if retired else inputs.spending_before_retirement
        ) * inflation_factor + medical
        tax = (income + social_security) * inputs.tax_rate
        pre_withdrawal_cash_flow = income + social_security - tax - spending

        if retired and pre_withdrawal_cash_flow < zero:
            shortfall = -pre_withdrawal_cash_flow
            net_cash_flow = -(shortfall / (one - inputs.withdrawal_tax_rate))
        else:
            net_cash_flow = pre_withdrawal_cash_flow

        if year == inputs.house_sale_year:
            net_cash_flow += inputs.house_sale_value
        if year == inputs.inheritance_year:
            net_cash_flow += inputs.inheritance_amount
        net_cash_flow += inputs.extra_annual_cash_flows.get(year, zero)

        return_rate = (
            inputs.return_rate_after_retirement if retired else inputs.return_rate_before_retirement
        )
        net_worth = (prior.net_worth + net_cash_flow) * (one + return_rate)

        rows.append(
            YearlyProjection(
                year=year,
                age=age,
                retired=retired,
                income=income,
                social_security=social_security,
                tax=tax,
                spending=spending,
                net_cash_flow=net_cash_flow,
                net_worth=net_worth,
            )
        )

    return rows
