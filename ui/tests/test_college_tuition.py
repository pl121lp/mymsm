from decimal import Decimal

from college_tuition import CollegeTuitionInputs, PersonCollegeCosts, compute_college_tuition_projection


def _inactive_person():
    return PersonCollegeCosts(
        start_year=9999,
        end_year=0,
        tuition_per_quarter=Decimal("0"),
        housing_per_quarter=Decimal("0"),
    )


def _inputs(**overrides):
    defaults = dict(
        starting_fund_value=Decimal("0"),
        annual_return_rate=Decimal("0"),
        contribution_per_quarter=Decimal("0"),
        contribution_end_year=0,
        person1=_inactive_person(),
        person2=_inactive_person(),
    )
    defaults.update(overrides)
    return CollegeTuitionInputs(**defaults)


def test_quarter_zero_is_a_snapshot_with_no_growth_or_cash_flow():
    inputs = _inputs(starting_fund_value=Decimal("5000"))

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=2)

    assert len(rows) == 1
    row = rows[0]
    assert row.year == 2024
    assert row.quarter == 2
    assert row.person1_cost == Decimal("0")
    assert row.person2_cost == Decimal("0")
    assert row.contribution == Decimal("0")
    assert row.net_cash_flow == Decimal("0")
    assert row.fund_value == Decimal("5000")


def test_person_active_only_within_start_and_end_year_inclusive():
    inputs = _inputs(
        person1=PersonCollegeCosts(
            start_year=2025,
            end_year=2026,
            tuition_per_quarter=Decimal("1000"),
            housing_per_quarter=Decimal("500"),
        ),
    )

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=4)
    by_yq = {(row.year, row.quarter): row for row in rows}

    assert by_yq[(2024, 4)].person1_cost == Decimal("0")
    assert by_yq[(2025, 1)].person1_cost == Decimal("1500")
    assert by_yq[(2025, 4)].person1_cost == Decimal("1500")
    assert by_yq[(2026, 1)].person1_cost == Decimal("1500")
    assert by_yq[(2026, 4)].person1_cost == Decimal("1500")
    assert (2027, 1) not in by_yq


def test_both_people_active_in_same_quarter_costs_are_summed():
    inputs = _inputs(
        person1=PersonCollegeCosts(
            start_year=2025, end_year=2026,
            tuition_per_quarter=Decimal("1000"), housing_per_quarter=Decimal("500"),
        ),
        person2=PersonCollegeCosts(
            start_year=2026, end_year=2027,
            tuition_per_quarter=Decimal("800"), housing_per_quarter=Decimal("400"),
        ),
    )

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=4)
    by_yq = {(row.year, row.quarter): row for row in rows}

    overlap = by_yq[(2026, 2)]
    assert overlap.person1_cost == Decimal("1500")
    assert overlap.person2_cost == Decimal("1200")
    assert overlap.net_cash_flow == Decimal("-2700")


def test_contribution_stops_after_contribution_end_year():
    inputs = _inputs(
        contribution_per_quarter=Decimal("2000"),
        contribution_end_year=2025,
    )

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=4)
    by_yq = {(row.year, row.quarter): row for row in rows}

    assert by_yq[(2025, 1)].contribution == Decimal("2000")
    assert by_yq[(2025, 4)].contribution == Decimal("2000")
    assert (2026, 1) not in by_yq


def test_quarterly_compounding_applies_quarter_root_of_annual_rate():
    inputs = _inputs(
        starting_fund_value=Decimal("1000"),
        annual_return_rate=Decimal("0.21550625"),  # exactly 5% compounded per quarter
        contribution_end_year=2025,
        contribution_per_quarter=Decimal("0"),
    )

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=4)
    values = [row.fund_value for row in rows]

    assert len(values) == 5
    assert values[0] == Decimal("1000")
    assert abs(values[1] - Decimal("1050.00000")) < Decimal("0.01")
    assert abs(values[2] - Decimal("1102.50000")) < Decimal("0.01")
    assert abs(values[3] - Decimal("1157.62500")) < Decimal("0.01")
    assert abs(values[4] - Decimal("1215.50625")) < Decimal("0.01")


def test_fund_goes_negative_without_flooring_when_costs_exceed_resources():
    inputs = _inputs(
        person1=PersonCollegeCosts(
            start_year=2025, end_year=2025,
            tuition_per_quarter=Decimal("1000"), housing_per_quarter=Decimal("0"),
        ),
    )

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=4)
    by_yq = {(row.year, row.quarter): row for row in rows}

    assert by_yq[(2025, 1)].fund_value == Decimal("-1000")
    assert by_yq[(2025, 4)].fund_value == Decimal("-4000")


def test_end_year_is_the_max_of_both_people_and_contribution_end_year():
    inputs = _inputs(
        person1=PersonCollegeCosts(
            start_year=2025, end_year=2025,
            tuition_per_quarter=Decimal("0"), housing_per_quarter=Decimal("0"),
        ),
        person2=PersonCollegeCosts(
            start_year=2030, end_year=2031,
            tuition_per_quarter=Decimal("0"), housing_per_quarter=Decimal("0"),
        ),
        contribution_end_year=2027,
    )

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=1)

    assert rows[-1].year == 2031
    assert rows[-1].quarter == 4


def test_person_never_active_when_start_year_after_end_year():
    inputs = _inputs(
        person1=PersonCollegeCosts(
            start_year=2027, end_year=2025,
            tuition_per_quarter=Decimal("1000"), housing_per_quarter=Decimal("1000"),
        ),
        contribution_end_year=2026,
    )

    rows = compute_college_tuition_projection(inputs, current_year=2024, current_quarter=1)

    assert all(row.person1_cost == Decimal("0") for row in rows)
