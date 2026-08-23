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
    assert row.investment_value == Decimal("5000")
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
    assert by_year[2024].investment_value == Decimal("1000")
    assert by_year[2024].net_worth == Decimal("1000")

    assert by_year[2025].retired is False
    assert by_year[2025].income == Decimal("1000")
    assert by_year[2025].net_cash_flow == Decimal("800")
    assert by_year[2025].investment_value == Decimal("1100")
    assert by_year[2025].net_worth == Decimal("1980")

    assert by_year[2026].retired is True
    assert by_year[2026].income == Decimal("0")
    assert by_year[2026].net_cash_flow == Decimal("-300")
    assert by_year[2026].investment_value == Decimal("1155")
    assert by_year[2026].net_worth == Decimal("1764")

    assert by_year[2027].retired is True
    assert by_year[2027].investment_value == Decimal("1212.75")
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
