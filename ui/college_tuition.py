"""Forward-looking college fund projection, driven by user-entered
assumptions rather than real transaction data (contrast with
models.compute_net_worth_series, which is historical). Steps quarter by
quarter, unlike projection.py's yearly Net Worth Projection.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import NamedTuple, Optional


@dataclass
class PersonCollegeCosts:
    start_year: int
    end_year: int
    tuition_per_quarter: Decimal
    housing_per_quarter: Decimal


@dataclass
class CollegeTuitionInputs:
    starting_fund_value: Decimal
    annual_return_rate: Decimal
    contribution_per_quarter: Decimal
    contribution_end_year: int
    person1: PersonCollegeCosts
    person2: PersonCollegeCosts


class QuarterlyProjection(NamedTuple):
    year: int
    quarter: int
    person1_cost: Decimal
    person2_cost: Decimal
    contribution: Decimal
    net_cash_flow: Decimal
    fund_value: Decimal


def _person_cost(person: PersonCollegeCosts, year: int) -> Decimal:
    if person.start_year <= year <= person.end_year:
        return person.tuition_per_quarter + person.housing_per_quarter
    return Decimal("0")


def _next_quarter(year: int, quarter: int) -> tuple[int, int]:
    return (year + 1, 1) if quarter == 4 else (year, quarter + 1)


def compute_college_tuition_projection(
    inputs: CollegeTuitionInputs,
    current_year: Optional[int] = None,
    current_quarter: Optional[int] = None,
) -> list[QuarterlyProjection]:
    """Quarter-by-quarter projection from the current quarter through Q4 of
    the latest of person1.end_year, person2.end_year, and
    contribution_end_year.

    Quarter 0 (the current quarter) is a snapshot at starting_fund_value
    with no cash flow or growth applied yet. Each later quarter adds that
    quarter's joint contribution (0 once past contribution_end_year) and
    subtracts each person's tuition + housing cost (0 unless
    person.start_year <= year <= person.end_year), then compounds the
    resulting fund_value at the quarterly-equivalent of annual_return_rate.
    fund_value is never floored at zero -- a shortfall keeps compounding as
    a negative balance, same convention as projection.py's net_worth.
    """
    today = date.today()
    if current_year is None:
        current_year = today.year
    if current_quarter is None:
        current_quarter = (today.month - 1) // 3 + 1

    end_year = max(inputs.person1.end_year, inputs.person2.end_year, inputs.contribution_end_year)
    quarterly_rate = (Decimal(1) + inputs.annual_return_rate) ** Decimal("0.25") - Decimal(1)
    zero = Decimal("0")

    rows = [
        QuarterlyProjection(
            year=current_year,
            quarter=current_quarter,
            person1_cost=zero,
            person2_cost=zero,
            contribution=zero,
            net_cash_flow=zero,
            fund_value=inputs.starting_fund_value,
        )
    ]

    year, quarter = current_year, current_quarter
    while (year, quarter) < (end_year, 4):
        year, quarter = _next_quarter(year, quarter)
        prior = rows[-1]

        person1_cost = _person_cost(inputs.person1, year)
        person2_cost = _person_cost(inputs.person2, year)
        contribution = inputs.contribution_per_quarter if year <= inputs.contribution_end_year else zero
        net_cash_flow = contribution - person1_cost - person2_cost
        fund_value = (prior.fund_value + net_cash_flow) * (Decimal(1) + quarterly_rate)

        rows.append(
            QuarterlyProjection(
                year=year,
                quarter=quarter,
                person1_cost=person1_cost,
                person2_cost=person2_cost,
                contribution=contribution,
                net_cash_flow=net_cash_flow,
                fund_value=fund_value,
            )
        )

    return rows
