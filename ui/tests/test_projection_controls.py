from datetime import date

import pytest

from projection_controls import ProjectionControlsPanel, default_projection_values


def test_default_projection_values_are_relative_to_today():
    values = default_projection_values(today=date(2024, 6, 15))
    assert values == {
        "birth_year": 1984,
        "end_year": 2064,
        "retirement_age": 65,
        "return_rate_before_retirement": 7.0,
        "return_rate_after_retirement": 5.0,
        "annual_income": 80000.0,
        "tax_rate": 20.0,
        "inflation_rate": 3.0,
        "spending_before_retirement": 60000.0,
        "spending_after_retirement": 50000.0,
        "social_security_annual_amount": 20000.0,
        "social_security_start_year": 2051,
        "house_sale_year": 2044,
        "inheritance_amount": 0.0,
        "inheritance_year": 2044,
        "medical_cost_after_retirement": 0.0,
        "medicare_age": 65,
        "withdrawal_tax_rate": 15.0,
    }


def test_panel_initializes_widgets_from_defaults(qapp):
    panel = ProjectionControlsPanel(today=date(2024, 6, 15))

    assert panel.birth_year_spinbox.value() == 1984
    assert panel.end_year_spinbox.value() == 2064
    assert panel.retirement_age_spinbox.value() == 65
    assert panel.starting_investment_value_spinbox.value() == pytest.approx(0.0)
    assert panel.return_rate_before_spinbox.value() == pytest.approx(7.0)
    assert panel.return_rate_after_spinbox.value() == pytest.approx(5.0)
    assert panel.annual_income_spinbox.value() == pytest.approx(80000.0)
    assert panel.tax_rate_spinbox.value() == pytest.approx(20.0)
    assert panel.inflation_rate_spinbox.value() == pytest.approx(3.0)
    assert panel.spending_before_spinbox.value() == pytest.approx(60000.0)
    assert panel.spending_after_spinbox.value() == pytest.approx(50000.0)
    assert panel.social_security_amount_spinbox.value() == pytest.approx(20000.0)
    assert panel.social_security_start_year_spinbox.value() == 2051
    assert panel.house_sale_year_spinbox.value() == 2044
    assert panel.inheritance_amount_spinbox.value() == pytest.approx(0.0)
    assert panel.inheritance_year_spinbox.value() == 2044
    assert panel.medical_cost_spinbox.value() == pytest.approx(0.0)
    assert panel.medicare_age_spinbox.value() == 65
    assert panel.withdrawal_tax_rate_spinbox.value() == pytest.approx(15.0)


def test_starting_investment_value_spinbox_is_not_editable(qapp):
    panel = ProjectionControlsPanel(today=date(2024, 6, 15))

    assert not panel.starting_investment_value_spinbox.isEnabled()


def test_house_account_combo_defaults_to_none(qapp):
    panel = ProjectionControlsPanel(today=date(2024, 6, 15))

    assert panel.values()["house_account_id"] is None


def test_set_house_accounts_populates_combo_and_can_be_selected(qapp):
    panel = ProjectionControlsPanel(today=date(2024, 6, 15))

    panel.set_house_accounts([(1, "House"), (2, "Cabin")])
    panel.house_account_combo.setCurrentIndex(2)

    assert panel.values()["house_account_id"] == 2


def test_set_values_selects_house_account_by_id(qapp):
    panel = ProjectionControlsPanel(today=date(2024, 6, 15))
    panel.set_house_accounts([(1, "House"), (2, "Cabin")])

    panel.set_values({"house_account_id": 2})

    assert panel.house_account_combo.currentData() == 2


def test_values_reflects_current_widget_state(qapp):
    panel = ProjectionControlsPanel(today=date(2024, 6, 15))
    panel.retirement_age_spinbox.setValue(70)
    panel.annual_income_spinbox.setValue(95000.0)

    values = panel.values()

    assert values["retirement_age"] == 70
    assert values["annual_income"] == pytest.approx(95000.0)


def test_values_and_set_values_round_trip_new_fields(qapp):
    panel = ProjectionControlsPanel(today=date(2024, 6, 15))

    panel.set_values(
        {
            "house_sale_year": 2040,
            "inheritance_amount": 25000.0,
            "inheritance_year": 2035,
            "medical_cost_after_retirement": 12000.0,
            "medicare_age": 67,
            "withdrawal_tax_rate": 18.5,
        }
    )
    values = panel.values()

    assert values["house_sale_year"] == 2040
    assert values["inheritance_amount"] == pytest.approx(25000.0)
    assert values["inheritance_year"] == 2035
    assert values["medical_cost_after_retirement"] == pytest.approx(12000.0)
    assert values["medicare_age"] == 67
    assert values["withdrawal_tax_rate"] == pytest.approx(18.5)


def test_set_values_updates_only_the_given_keys(qapp):
    panel = ProjectionControlsPanel(today=date(2024, 6, 15))

    panel.set_values({"retirement_age": 62})

    assert panel.retirement_age_spinbox.value() == 62
    assert panel.end_year_spinbox.value() == 2064


def test_clicking_update_button_emits_updated_signal(qapp):
    panel = ProjectionControlsPanel(today=date(2024, 6, 15))
    calls = []
    panel.updated.connect(lambda: calls.append(True))

    panel.update_button.click()

    assert calls == [True]
