from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtWidgets import QDialog

from college_tuition_controls import CollegeTuitionControlsPanel, default_college_tuition_values


def test_default_college_tuition_values_are_relative_to_today():
    values = default_college_tuition_values(today=date(2024, 6, 15))
    assert values == {
        "annual_return_rate": 6.0,
        "contribution_per_quarter": 0.0,
        "contribution_end_year": 2036,
        "person1_start_year": 2029,
        "person1_end_year": 2033,
        "person1_tuition_per_quarter": 10000.0,
        "person1_housing_per_quarter": 4000.0,
        "person2_start_year": 2032,
        "person2_end_year": 2036,
        "person2_tuition_per_quarter": 10000.0,
        "person2_housing_per_quarter": 4000.0,
    }


def test_panel_initializes_widgets_from_defaults(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))

    assert panel.annual_return_rate_spinbox.value() == pytest.approx(6.0)
    assert panel.contribution_per_quarter_spinbox.value() == pytest.approx(0.0)
    assert panel.contribution_end_year_spinbox.value() == 2036
    assert panel.person1_start_year_spinbox.value() == 2029
    assert panel.person1_end_year_spinbox.value() == 2033
    assert panel.person1_tuition_per_quarter_spinbox.value() == pytest.approx(10000.0)
    assert panel.person1_housing_per_quarter_spinbox.value() == pytest.approx(4000.0)
    assert panel.person2_start_year_spinbox.value() == 2032
    assert panel.person2_end_year_spinbox.value() == 2036
    assert panel.person2_tuition_per_quarter_spinbox.value() == pytest.approx(10000.0)
    assert panel.person2_housing_per_quarter_spinbox.value() == pytest.approx(4000.0)


def test_starting_fund_value_spinbox_is_not_editable(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))
    assert not panel.starting_fund_value_spinbox.isEnabled()


def test_set_accounts_defaults_to_all_selected_and_sums_balances(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))

    panel.set_accounts(
        [(1, "529 Plan"), (2, "Brokerage")],
        {1: Decimal("1000.00"), 2: Decimal("2500.50")},
    )

    assert panel.values()["selected_account_ids"] == [1, 2]
    assert panel.starting_fund_value_spinbox.value() == pytest.approx(3500.50)


def test_set_accounts_keeps_only_intersection_of_prior_selection(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))
    panel.set_accounts([(1, "529 Plan"), (2, "Brokerage")], {1: Decimal("1000.00"), 2: Decimal("2000.00")})
    panel.set_values({"selected_account_ids": [2]})

    panel.set_accounts([(2, "Brokerage")], {2: Decimal("2000.00")})

    assert panel.values()["selected_account_ids"] == [2]
    assert panel.starting_fund_value_spinbox.value() == pytest.approx(2000.00)


def test_set_values_restores_selected_account_ids_and_recomputes_total(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))
    panel.set_accounts(
        [(1, "529 Plan"), (2, "Brokerage")],
        {1: Decimal("1000.00"), 2: Decimal("2000.00")},
    )

    panel.set_values({"selected_account_ids": [1]})

    assert panel.values()["selected_account_ids"] == [1]
    assert panel.starting_fund_value_spinbox.value() == pytest.approx(1000.00)


def test_values_and_set_values_round_trip(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))

    panel.set_values(
        {
            "annual_return_rate": 5.5,
            "contribution_per_quarter": 1500.0,
            "contribution_end_year": 2040,
            "person1_start_year": 2030,
            "person1_end_year": 2034,
            "person1_tuition_per_quarter": 12000.0,
            "person1_housing_per_quarter": 5000.0,
            "person2_start_year": 2033,
            "person2_end_year": 2037,
            "person2_tuition_per_quarter": 13000.0,
            "person2_housing_per_quarter": 5500.0,
        }
    )
    values = panel.values()

    assert values["annual_return_rate"] == pytest.approx(5.5)
    assert values["contribution_per_quarter"] == pytest.approx(1500.0)
    assert values["contribution_end_year"] == 2040
    assert values["person1_start_year"] == 2030
    assert values["person1_end_year"] == 2034
    assert values["person1_tuition_per_quarter"] == pytest.approx(12000.0)
    assert values["person1_housing_per_quarter"] == pytest.approx(5000.0)
    assert values["person2_start_year"] == 2033
    assert values["person2_end_year"] == 2037
    assert values["person2_tuition_per_quarter"] == pytest.approx(13000.0)
    assert values["person2_housing_per_quarter"] == pytest.approx(5500.0)


def test_set_values_updates_only_the_given_keys(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))

    panel.set_values({"contribution_end_year": 2050})

    assert panel.contribution_end_year_spinbox.value() == 2050
    assert panel.person1_start_year_spinbox.value() == 2029


def test_select_accounts_button_opens_dialog_and_applies_selection(qapp, monkeypatch):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))
    panel.set_accounts(
        [(1, "529 Plan"), (2, "Brokerage")],
        {1: Decimal("1000.00"), 2: Decimal("2000.00")},
    )

    class _FakeDialog:
        def __init__(self, accounts, selected_ids, parent=None):
            self.accounts = accounts
            self.selected_ids = selected_ids

        def exec(self):
            return QDialog.Accepted

        def selected_account_ids(self):
            return {1}

    import college_tuition_controls

    monkeypatch.setattr(college_tuition_controls, "AccountFilterDialog", _FakeDialog)
    panel.select_accounts_button.click()

    assert panel.values()["selected_account_ids"] == [1]
    assert panel.starting_fund_value_spinbox.value() == pytest.approx(1000.00)


def test_canceling_select_accounts_dialog_leaves_selection_unchanged(qapp, monkeypatch):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))
    panel.set_accounts(
        [(1, "529 Plan"), (2, "Brokerage")],
        {1: Decimal("1000.00"), 2: Decimal("2000.00")},
    )

    class _FakeDialog:
        def __init__(self, accounts, selected_ids, parent=None):
            pass

        def exec(self):
            return QDialog.Rejected

        def selected_account_ids(self):
            return {1}

    import college_tuition_controls

    monkeypatch.setattr(college_tuition_controls, "AccountFilterDialog", _FakeDialog)
    panel.select_accounts_button.click()

    assert panel.values()["selected_account_ids"] == [1, 2]


def test_clicking_update_button_emits_updated_signal(qapp):
    panel = CollegeTuitionControlsPanel(today=date(2024, 6, 15))
    calls = []
    panel.updated.connect(lambda: calls.append(True))

    panel.update_button.click()

    assert calls == [True]
