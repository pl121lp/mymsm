from decimal import Decimal

from projection import ProjectionInputs, compute_projection


def _inputs(**overrides):
    defaults = dict(
        birth_year=2000,
        end_year=2024,
        retirement_age=100,
        starting_investment_value=Decimal("0"),
        return_rate_before_retirement=Decimal("0"),
        return_rate_after_retirement=Decimal("0"),
        annual_income=Decimal("0"),
        tax_rate=Decimal("0"),
        inflation_rate=Decimal("0"),
        spending_before_retirement=Decimal("0"),
        spending_after_retirement=Decimal("0"),
        social_security_annual_amount=Decimal("0"),
        social_security_start_year=9999,
        house_sale_value=Decimal("0"),
        house_sale_year=999999,
        inheritance_amount=Decimal("0"),
        inheritance_year=999999,
        medical_cost_after_retirement=Decimal("0"),
        medicare_age=65,
        withdrawal_tax_rate=Decimal("0"),
    )
    defaults.update(overrides)
    return ProjectionInputs(**defaults)


def test_year_zero_is_a_snapshot_with_no_growth_or_cash_flow():
    inputs = _inputs(
        birth_year=1990,
        end_year=2024,
        retirement_age=40,
        starting_investment_value=Decimal("5000"),
    )

    rows = compute_projection(inputs, current_year=2024)

    assert len(rows) == 1
    row = rows[0]
    assert row.year == 2024
    assert row.age == 34
    assert row.retired is False
    assert row.income == Decimal("0")
    assert row.social_security == Decimal("0")
    assert row.tax == Decimal("0")
    assert row.spending == Decimal("0")
    assert row.net_cash_flow == Decimal("0")
    assert row.net_worth == Decimal("5000")


def test_pre_and_post_retirement_transition_switches_income_and_return_rate():
    inputs = _inputs(
        birth_year=2000,
        end_year=2027,
        retirement_age=26,
        starting_investment_value=Decimal("1000"),
        return_rate_before_retirement=Decimal("0.10"),
        return_rate_after_retirement=Decimal("0.05"),
        annual_income=Decimal("1000"),
        spending_before_retirement=Decimal("200"),
        spending_after_retirement=Decimal("300"),
    )

    rows = compute_projection(inputs, current_year=2024)
    by_year = {row.year: row for row in rows}

    assert by_year[2024].retired is False
    assert by_year[2024].net_worth == Decimal("1000")

    assert by_year[2025].retired is False
    assert by_year[2025].income == Decimal("1000")
    assert by_year[2025].net_cash_flow == Decimal("800")
    assert by_year[2025].net_worth == Decimal("1980")

    assert by_year[2026].retired is True
    assert by_year[2026].income == Decimal("0")
    assert by_year[2026].net_cash_flow == Decimal("-300")
    assert by_year[2026].net_worth == Decimal("1764")

    assert by_year[2027].retired is True
    assert by_year[2027].net_worth == Decimal("1537.20")


def test_inflation_escalates_income_and_spending():
    inputs = _inputs(
        birth_year=2000,
        end_year=2026,
        retirement_age=100,
        annual_income=Decimal("1000"),
        spending_before_retirement=Decimal("100"),
        inflation_rate=Decimal("0.10"),
    )

    rows = compute_projection(inputs, current_year=2024)
    by_year = {row.year: row for row in rows}

    assert by_year[2025].income == Decimal("1100")
    assert by_year[2025].spending == Decimal("110")
    assert by_year[2025].net_worth == Decimal("990")

    assert by_year[2026].income == Decimal("1210")
    assert by_year[2026].spending == Decimal("121")
    assert by_year[2026].net_worth == Decimal("2079")


def test_social_security_starts_only_at_configured_year():
    inputs = _inputs(
        birth_year=1950,
        end_year=2027,
        retirement_age=200,
        social_security_annual_amount=Decimal("500"),
        social_security_start_year=2026,
    )

    rows = compute_projection(inputs, current_year=2024)
    by_year = {row.year: row for row in rows}

    assert by_year[2025].social_security == Decimal("0")
    assert by_year[2025].net_worth == Decimal("0")
    assert by_year[2026].social_security == Decimal("500")
    assert by_year[2026].net_worth == Decimal("500")
    assert by_year[2027].net_worth == Decimal("1000")


def test_tax_applies_to_income_and_social_security_only():
    inputs = _inputs(
        birth_year=1950,
        end_year=2025,
        retirement_age=200,
        annual_income=Decimal("1000"),
        social_security_annual_amount=Decimal("500"),
        social_security_start_year=2024,
        tax_rate=Decimal("0.20"),
    )

    rows = compute_projection(inputs, current_year=2024)
    row = rows[-1]

    assert row.tax == Decimal("300")
    assert row.net_cash_flow == Decimal("1200")
    assert row.net_worth == Decimal("1200")


def test_net_worth_goes_negative_without_flooring_when_spending_exceeds_resources():
    inputs = _inputs(
        birth_year=2000,
        end_year=2026,
        retirement_age=100,
        spending_before_retirement=Decimal("1000"),
        return_rate_before_retirement=Decimal("0.10"),
    )

    rows = compute_projection(inputs, current_year=2024)
    by_year = {row.year: row for row in rows}

    assert by_year[2025].net_worth == Decimal("-1100")
    assert by_year[2026].net_worth == Decimal("-2310")


def test_house_sale_adds_lump_sum_in_sale_year_only():
    inputs = _inputs(
        birth_year=2000,
        end_year=2027,
        retirement_age=100,
        house_sale_value=Decimal("5000"),
        house_sale_year=2025,
    )

    rows = compute_projection(inputs, current_year=2024)
    by_year = {row.year: row for row in rows}

    assert by_year[2024].net_worth == Decimal("0")
    assert by_year[2025].net_worth == Decimal("5000")
    assert by_year[2026].net_worth == Decimal("5000")


def test_inheritance_adds_lump_sum_in_inheritance_year_only():
    inputs = _inputs(
        birth_year=2000,
        end_year=2027,
        retirement_age=100,
        inheritance_amount=Decimal("2000"),
        inheritance_year=2026,
    )

    rows = compute_projection(inputs, current_year=2024)
    by_year = {row.year: row for row in rows}

    assert by_year[2025].net_worth == Decimal("0")
    assert by_year[2026].net_worth == Decimal("2000")
    assert by_year[2027].net_worth == Decimal("2000")


def test_medical_costs_apply_only_between_retirement_and_medicare_age():
    inputs = _inputs(
        birth_year=1960,
        end_year=2028,
        retirement_age=65,
        medical_cost_after_retirement=Decimal("1000"),
        medicare_age=67,
    )

    rows = compute_projection(inputs, current_year=2024)
    by_year = {row.year: row for row in rows}

    assert by_year[2025].retired is True
    assert by_year[2025].age == 65
    assert by_year[2025].spending == Decimal("1000")

    assert by_year[2026].age == 66
    assert by_year[2026].spending == Decimal("1000")

    assert by_year[2027].age == 67
    assert by_year[2027].spending == Decimal("0")


def test_withdrawal_tax_grosses_up_retirement_shortfall():
    inputs = _inputs(
        birth_year=2000,
        end_year=2025,
        retirement_age=24,
        starting_investment_value=Decimal("5000"),
        spending_after_retirement=Decimal("800"),
        withdrawal_tax_rate=Decimal("0.20"),
    )

    rows = compute_projection(inputs, current_year=2024)
    row = rows[-1]

    assert row.retired is True
    assert row.net_cash_flow == Decimal("-1000")
    assert row.net_worth == Decimal("4000")


def test_withdrawal_tax_not_applied_when_retirement_income_covers_spending():
    inputs = _inputs(
        birth_year=2000,
        end_year=2025,
        retirement_age=24,
        social_security_annual_amount=Decimal("1000"),
        social_security_start_year=2024,
        spending_after_retirement=Decimal("500"),
        withdrawal_tax_rate=Decimal("0.50"),
    )

    rows = compute_projection(inputs, current_year=2024)
    row = rows[-1]

    assert row.net_cash_flow == Decimal("500")
    assert row.net_worth == Decimal("500")


def test_withdrawal_tax_not_applied_before_retirement():
    inputs = _inputs(
        birth_year=2000,
        end_year=2025,
        retirement_age=100,
        spending_before_retirement=Decimal("800"),
        withdrawal_tax_rate=Decimal("0.50"),
    )

    rows = compute_projection(inputs, current_year=2024)
    row = rows[-1]

    assert row.retired is False
    assert row.net_cash_flow == Decimal("-800")
    assert row.net_worth == Decimal("-800")


def test_house_sale_is_not_grossed_up_by_withdrawal_tax():
    inputs = _inputs(
        birth_year=2000,
        end_year=2025,
        retirement_age=24,
        starting_investment_value=Decimal("5000"),
        spending_after_retirement=Decimal("800"),
        withdrawal_tax_rate=Decimal("0.20"),
        house_sale_value=Decimal("2000"),
        house_sale_year=2025,
    )

    rows = compute_projection(inputs, current_year=2024)
    row = rows[-1]

    assert row.net_cash_flow == Decimal("1000")
    assert row.net_worth == Decimal("6000")
