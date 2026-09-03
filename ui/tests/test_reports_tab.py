import functools
from datetime import date

import pytest
from PySide6.QtCore import QDate, QItemSelectionModel, Qt
from PySide6.QtWidgets import QApplication, QDialog, QScrollArea, QSizePolicy

import reports_tab
import theme
from college_tuition_settings import (
    load_college_tuition_settings as _real_load_college_tuition_settings,
    save_college_tuition_settings as _real_save_college_tuition_settings,
)
from projection_settings import (
    DEFAULT_PROFILE_NAME,
    load_projection_profiles as _real_load_projection_profiles,
    save_projection_profiles as _real_save_projection_profiles,
)
from reports_tab import REPORTS, ReportsPane
from rsu_tax_settings import load_rsu_tax_settings, save_rsu_tax_settings


def _select_net_worth_report(pane):
    pane.list_view.selectionModel().select(
        pane.list_model.index(0, 0), QItemSelectionModel.ClearAndSelect
    )
    _wait_for_net_worth_report(pane)


def _wait_for_net_worth_report(pane):
    """Net-worth report computation runs on a background thread (see
    busy_indicator.run_in_background), and loading chains a second one
    (account histories, then the chart series) -- keep waiting and letting
    Qt deliver queued completion signals until no new worker gets chained.
    Loading itself is deferred via QTimer.singleShot(0, ...) so the spinner
    paints before the synchronous account fetch runs; process events first
    so that timer fires."""
    QApplication.processEvents()
    for _ in range(5):
        worker = pane._net_worth_worker
        if worker is None:
            break
        worker.wait()
        QApplication.processEvents()
        if pane._net_worth_worker is worker:
            break


def _select_spending_report(pane):
    pane.list_view.selectionModel().select(
        pane.list_model.index(1, 0), QItemSelectionModel.ClearAndSelect
    )


def _select_income_report(pane):
    pane.list_view.selectionModel().select(
        pane.list_model.index(2, 0), QItemSelectionModel.ClearAndSelect
    )


def _select_investment_report(pane):
    pane.list_view.selectionModel().select(
        pane.list_model.index(3, 0), QItemSelectionModel.ClearAndSelect
    )


def _select_college_tuition_report(pane):
    pane.list_view.selectionModel().select(
        pane.list_model.index(5, 0), QItemSelectionModel.ClearAndSelect
    )


def _select_recurring_report(pane):
    pane.list_view.selectionModel().select(
        pane.list_model.index(7, 0), QItemSelectionModel.ClearAndSelect
    )
    # Loading is deferred via QTimer.singleShot(0, ...) so the spinner paints
    # before the synchronous transaction fetch runs; process events so that
    # timer fires before callers inspect the result.
    QApplication.processEvents()


def _wait_for_recurring_report(pane):
    """Recurring-report computation runs on a background thread (see
    busy_indicator.run_in_background); block until it finishes and let Qt
    deliver its queued completion signal before asserting on the result."""
    worker = pane._recurring_worker
    if worker is not None:
        worker.wait()
    QApplication.processEvents()


def _add_recurring_transactions(conn):
    conn.execute(
        "INSERT INTO transactions VALUES "
        "(5000, 1, 20, 100, '2024-01-15', -52.30, 'monthly charge', NULL, NULL, NULL, NULL, NULL), "
        "(5001, 1, 20, 100, '2024-02-15', -52.30, 'monthly charge', NULL, NULL, NULL, NULL, NULL)"
    )


def _add_income_transactions(conn):
    conn.execute(
        "INSERT INTO categories VALUES (30, 'Salary'), (31, 'Freelance')"
    )
    conn.execute(
        "INSERT INTO transactions VALUES "
        "(2000, 1, 30, NULL, '2024-03-01', 1200.00, 'paycheck', NULL, NULL, NULL, NULL, NULL), "
        "(2001, 2, 31, NULL, '2024-03-15', 300.00, 'contract work', NULL, NULL, NULL, NULL, NULL)"
    )


def _table_cell(view, row, col):
    return view.model().data(view.model().index(row, col), Qt.DisplayRole)


def test_reports_list_view_supports_copy(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_view.contextMenuPolicy() == Qt.CustomContextMenu


def test_reports_list_shows_net_worth_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.rowCount() == len(REPORTS)
    assert pane.list_model.data(pane.list_model.index(0, 0)) == "1. Net worth over time"


def test_reports_list_shows_spending_by_category_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.data(pane.list_model.index(1, 0)) == "2. Spending by category"


def test_reports_list_shows_income_by_category_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.data(pane.list_model.index(2, 0)) == "3. Income by category"


def test_reports_list_shows_investment_analysis_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.data(pane.list_model.index(3, 0)) == "4. Investment analysis"


def test_reports_list_shows_recurring_subscriptions_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.data(pane.list_model.index(7, 0)) == "8. Recurring / Subscriptions"


def test_select_report_by_number_selects_the_matching_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    pane.select_report_by_number(5)

    assert pane._active_report_id == reports_tab.NET_WORTH_PROJECTION_REPORT_ID


def test_select_report_by_number_ignores_out_of_range_numbers(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.select_report_by_number(1)

    pane.select_report_by_number(len(REPORTS) + 1)

    assert pane._active_report_id == reports_tab.NET_WORTH_REPORT_ID


def test_empty_chart_panel_uses_dark_theme_when_dark_mode_is_active(qapp, dict_conn):
    theme.apply_theme(qapp, True)
    try:
        pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
        assert pane.chart_view.chart().theme() == theme.chart_theme()

        _select_net_worth_report(pane)
        pane.list_view.selectionModel().clearSelection()
        assert pane.chart_view.chart().theme() == theme.chart_theme()
    finally:
        theme.apply_theme(qapp, False)


def test_selecting_net_worth_report_draws_a_bar_chart(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_net_worth_report(pane)
    chart = pane.chart_view.chart()
    assert chart is not None
    assert len(chart.series()) == 1


def test_selecting_net_worth_report_defaults_date_range_to_full_history(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_net_worth_report(pane)
    assert pane.start_date_edit.date().toPython() == date(2024, 1, 10)
    assert pane.end_date_edit.date().toPython() == date(2024, 3, 15)
    assert pane.range_label.text() == "Showing 2024-01-10 to 2024-03-15"


def test_net_worth_report_samples_every_other_month(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_net_worth_report(pane)
    bar_set = pane.chart_view.chart().series()[0].barSets()[0]
    # 2024-01-10 to 2024-03-15, stepping by 2 months: 01-10, 03-10, 03-15.
    assert bar_set.count() == 3


def test_updating_range_redraws_chart_for_narrower_window(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_net_worth_report(pane)

    pane.start_date_edit.setDate(QDate(2024, 2, 1))
    pane.end_date_edit.setDate(QDate(2024, 3, 1))
    pane.update_range_button.click()
    _wait_for_net_worth_report(pane)

    assert pane.range_label.text() == "Showing 2024-02-01 to 2024-03-01"
    bar_set = pane.chart_view.chart().series()[0].barSets()[0]
    assert bar_set.count() == 2


def test_updating_range_with_start_after_end_reports_error_and_keeps_chart(qapp, dict_conn):
    errors = []
    pane = ReportsPane(dict_conn, report_error=errors.append, to_usd=lambda cur, amt: amt)
    _select_net_worth_report(pane)

    bar_set_before = pane.chart_view.chart().series()[0].barSets()[0]
    count_before = bar_set_before.count()

    pane.start_date_edit.setDate(QDate(2024, 3, 15))
    pane.end_date_edit.setDate(QDate(2024, 1, 10))
    pane.update_range_button.click()

    assert errors == ["Start date must be on or before end date."]
    assert pane.range_label.text() == "Showing 2024-01-10 to 2024-03-15"
    bar_set_after = pane.chart_view.chart().series()[0].barSets()[0]
    assert bar_set_after.count() == count_before


def test_net_worth_report_excludes_account_before_its_date_opened(qapp, dict_conn):
    baseline = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_net_worth_report(baseline)
    baseline_bar_set = baseline.chart_view.chart().series()[0].barSets()[0]
    baseline_first = baseline_bar_set.at(0)

    dict_conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id, date_opened) VALUES "
        "(5, 'New Loan', '6', FALSE, -50000.00, 'USD', NULL, '2024-02-01')"
    )
    dict_conn.execute(
        "INSERT INTO transactions VALUES "
        "(5000, 5, NULL, NULL, '2024-02-15', 300.00, 'payment', NULL, NULL, NULL, NULL, NULL)"
    )

    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_net_worth_report(pane)
    assert pane.range_label.text() == "Showing 2024-01-10 to 2024-03-15"
    bar_set = pane.chart_view.chart().series()[0].barSets()[0]

    # The loan didn't exist yet on the report's earliest date, so it
    # shouldn't drag that bar down by its full -50000 opening balance.
    assert bar_set.at(0) == pytest.approx(baseline_first)
    # By the final date it has been open and active, so it should count.
    assert bar_set.at(bar_set.count() - 1) < -40000


def test_net_worth_report_excludes_closed_account_after_its_last_transaction(qapp, dict_conn):
    baseline = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_net_worth_report(baseline)
    baseline_bar_set = baseline.chart_view.chart().series()[0].barSets()[0]
    baseline_last = baseline_bar_set.at(baseline_bar_set.count() - 1)

    dict_conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id, date_opened) VALUES "
        "(5, 'Old Closed Loan', '6', TRUE, -5000.00, 'USD', NULL, '2024-01-01')"
    )
    dict_conn.execute(
        "INSERT INTO transactions VALUES "
        # Leaves a -4800 residual that was never reconciled to zero, as
        # happens when a loan is closed out by a refinance.
        "(5000, 5, NULL, NULL, '2024-01-20', 200.00, 'partial payoff', NULL, NULL, NULL, NULL, NULL)"
    )

    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_net_worth_report(pane)
    assert pane.range_label.text() == "Showing 2024-01-10 to 2024-03-15"
    bar_set = pane.chart_view.chart().series()[0].barSets()[0]

    # The closed loan's stale -4800 balance shouldn't still be dragging
    # down net worth on the report's final (present-day) date.
    assert bar_set.at(bar_set.count() - 1) == pytest.approx(baseline_last)


def test_selecting_spending_report_shows_table_and_hides_chart(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_net_worth_report(pane)
    assert pane.chart_view.isVisible()

    _select_spending_report(pane)
    assert pane.category_table_view.isVisible()
    assert not pane.chart_view.isVisible()


def test_selecting_spending_report_defaults_date_range_to_full_history(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_spending_report(pane)
    assert pane.start_date_edit.date().toPython() == date(2024, 3, 1)
    assert pane.end_date_edit.date().toPython() == date(2024, 3, 15)
    assert pane.range_label.text() == "Showing 2024-03-01 to 2024-03-15"


def test_selecting_spending_report_sorts_categories_by_spending_descending(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_spending_report(pane)

    view = pane.category_table_view
    assert view.model().rowCount() == 2
    assert _table_cell(view, 0, 0) == "Utilities"
    assert _table_cell(view, 0, 1) == "75.00"
    assert _table_cell(view, 1, 0) == "Groceries"
    assert _table_cell(view, 1, 1) == "72.30"


def test_updating_range_recomputes_spending_table_for_narrower_window(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_spending_report(pane)

    pane.start_date_edit.setDate(QDate(2024, 3, 12))
    pane.end_date_edit.setDate(QDate(2024, 3, 31))
    pane.update_range_button.click()

    assert pane.range_label.text() == "Showing 2024-03-12 to 2024-03-31"
    view = pane.category_table_view
    assert view.model().rowCount() == 1
    assert _table_cell(view, 0, 0) == "Groceries"
    assert _table_cell(view, 0, 1) == "52.30"


def test_updating_spending_range_with_start_after_end_reports_error_and_keeps_table(qapp, dict_conn):
    errors = []
    pane = ReportsPane(dict_conn, report_error=errors.append, to_usd=lambda cur, amt: amt)
    _select_spending_report(pane)

    pane.start_date_edit.setDate(QDate(2024, 3, 15))
    pane.end_date_edit.setDate(QDate(2024, 3, 1))
    pane.update_range_button.click()

    assert errors == ["Start date must be on or before end date."]
    assert pane.range_label.text() == "Showing 2024-03-01 to 2024-03-15"
    assert pane.category_table_view.model().rowCount() == 2


def test_spending_report_defaults_to_table_view_with_selector_hidden_elsewhere(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_net_worth_report(pane)
    assert not pane.view_selector.isVisible()

    _select_spending_report(pane)
    assert pane.view_selector.isVisible()
    assert pane.view_selector.currentText() == "Table"
    assert pane.category_table_view.isVisible()
    assert not pane.chart_view.isVisible()


def test_switching_spending_report_to_pie_chart_shows_chart_and_hides_table(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_spending_report(pane)

    pane.view_selector.setCurrentText("Pie Chart")

    assert pane.chart_view.isVisible()
    assert not pane.category_table_view.isVisible()
    series = pane.chart_view.chart().series()[0]
    assert len(series.slices()) == 2
    assert series.slices()[0].label() == "Utilities"


def test_updating_range_recomputes_pie_chart_for_narrower_window(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_spending_report(pane)
    pane.view_selector.setCurrentText("Pie Chart")

    pane.start_date_edit.setDate(QDate(2024, 3, 12))
    pane.end_date_edit.setDate(QDate(2024, 3, 31))
    pane.update_range_button.click()

    series = pane.chart_view.chart().series()[0]
    assert len(series.slices()) == 1
    assert series.slices()[0].label() == "Groceries"


class _FakeInvestmentFilterDialog:
    result = QDialog.Accepted
    last_init_args = None

    def __init__(self, investment_names, selected_names, parent=None):
        _FakeInvestmentFilterDialog.last_init_args = (set(investment_names), set(selected_names))
        self._selection = {"Vanguard Total Stock Market Index"}

    def exec(self):
        return self.__class__.result

    def selected_investments(self):
        return self._selection


def test_custom_investments_button_hidden_for_net_worth_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_net_worth_report(pane)
    assert not pane.custom_investments_button.isVisible()


def test_custom_investments_button_visible_for_investment_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_investment_report(pane)
    assert pane.custom_investments_button.isVisible()


def test_custom_investments_dialog_offers_all_investments_preselected(qapp, dict_conn, monkeypatch):
    dict_conn.execute("INSERT INTO securities VALUES (502, 'Small Cap Fund')")
    dict_conn.execute(
        "INSERT INTO transactions VALUES "
        "(5000, 3, NULL, NULL, '2024-01-10', 100.00, NULL, 502, '1', 1.0, 100.00, NULL)"
    )
    monkeypatch.setattr(reports_tab, "InvestmentFilterDialog", _FakeInvestmentFilterDialog)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_investment_report(pane)

    pane.custom_investments_button.click()

    all_names, selected_names = _FakeInvestmentFilterDialog.last_init_args
    assert all_names == {"Vanguard Total Stock Market Index", "Small Cap Fund"}
    assert selected_names == {"Vanguard Total Stock Market Index", "Small Cap Fund"}


def test_accepting_custom_investments_filters_table(qapp, dict_conn, monkeypatch):
    dict_conn.execute("INSERT INTO securities VALUES (502, 'Small Cap Fund')")
    dict_conn.execute(
        "INSERT INTO transactions VALUES "
        "(5000, 3, NULL, NULL, '2024-01-10', 100.00, NULL, 502, '1', 1.0, 100.00, NULL)"
    )
    monkeypatch.setattr(reports_tab, "InvestmentFilterDialog", _FakeInvestmentFilterDialog)
    _FakeInvestmentFilterDialog.result = QDialog.Accepted
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_investment_report(pane)

    pane.custom_investments_button.click()

    view = pane.investment_table_view
    assert view.model().rowCount() == 1
    assert _table_cell(view, 0, 0) == "Vanguard Total Stock Market Index"


def test_canceling_custom_investments_leaves_selection_unchanged(qapp, dict_conn, monkeypatch):
    dict_conn.execute("INSERT INTO securities VALUES (502, 'Small Cap Fund')")
    dict_conn.execute(
        "INSERT INTO transactions VALUES "
        "(5000, 3, NULL, NULL, '2024-01-10', 100.00, NULL, 502, '1', 1.0, 100.00, NULL)"
    )
    monkeypatch.setattr(reports_tab, "InvestmentFilterDialog", _FakeInvestmentFilterDialog)
    _FakeInvestmentFilterDialog.result = QDialog.Rejected
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_investment_report(pane)

    pane.custom_investments_button.click()

    assert pane.investment_table_view.model().rowCount() == 2


def test_reselecting_investment_report_resets_investment_filter_to_all(qapp, dict_conn, monkeypatch):
    dict_conn.execute("INSERT INTO securities VALUES (502, 'Small Cap Fund')")
    dict_conn.execute(
        "INSERT INTO transactions VALUES "
        "(5000, 3, NULL, NULL, '2024-01-10', 100.00, NULL, 502, '1', 1.0, 100.00, NULL)"
    )
    monkeypatch.setattr(reports_tab, "InvestmentFilterDialog", _FakeInvestmentFilterDialog)
    _FakeInvestmentFilterDialog.result = QDialog.Accepted
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_investment_report(pane)
    pane.custom_investments_button.click()
    assert pane.investment_table_view.model().rowCount() == 1

    _select_net_worth_report(pane)
    _select_investment_report(pane)

    assert pane.investment_table_view.model().rowCount() == 2


class _FakeCategoryFilterDialog:
    result = QDialog.Accepted
    last_init_args = None

    def __init__(self, category_names, selected_names, parent=None):
        _FakeCategoryFilterDialog.last_init_args = (set(category_names), set(selected_names))
        self._selection = {"Utilities"}

    def exec(self):
        return self.__class__.result

    def selected_categories(self):
        return self._selection


def test_custom_categories_button_hidden_for_net_worth_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_net_worth_report(pane)
    assert not pane.custom_categories_button.isVisible()


def test_custom_categories_button_visible_for_spending_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_spending_report(pane)
    assert pane.custom_categories_button.isVisible()


def test_custom_categories_dialog_offers_all_categories_preselected(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "CategoryFilterDialog", _FakeCategoryFilterDialog)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_spending_report(pane)

    pane.custom_categories_button.click()

    all_names, selected_names = _FakeCategoryFilterDialog.last_init_args
    assert all_names == {"Utilities", "Groceries"}
    assert selected_names == {"Utilities", "Groceries"}


def test_accepting_custom_categories_filters_table_and_chart(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "CategoryFilterDialog", _FakeCategoryFilterDialog)
    _FakeCategoryFilterDialog.result = QDialog.Accepted
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_spending_report(pane)
    pane.view_selector.setCurrentText("Pie Chart")

    pane.custom_categories_button.click()

    view = pane.category_table_view
    assert view.model().rowCount() == 1
    assert _table_cell(view, 0, 0) == "Utilities"
    series = pane.chart_view.chart().series()[0]
    assert len(series.slices()) == 1
    assert series.slices()[0].label() == "Utilities"


def test_canceling_custom_categories_leaves_selection_unchanged(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "CategoryFilterDialog", _FakeCategoryFilterDialog)
    _FakeCategoryFilterDialog.result = QDialog.Rejected
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_spending_report(pane)

    pane.custom_categories_button.click()

    view = pane.category_table_view
    assert view.model().rowCount() == 2


def test_reselecting_spending_report_resets_category_filter_to_all(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "CategoryFilterDialog", _FakeCategoryFilterDialog)
    _FakeCategoryFilterDialog.result = QDialog.Accepted
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_spending_report(pane)
    pane.custom_categories_button.click()
    assert pane.category_table_view.model().rowCount() == 1

    _select_net_worth_report(pane)
    _select_spending_report(pane)

    assert pane.category_table_view.model().rowCount() == 2


def test_selecting_income_report_shows_table_and_hides_chart(qapp, dict_conn):
    _add_income_transactions(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_net_worth_report(pane)
    assert pane.chart_view.isVisible()

    _select_income_report(pane)
    assert pane.category_table_view.isVisible()
    assert not pane.chart_view.isVisible()


def test_selecting_income_report_defaults_date_range_to_full_history(qapp, dict_conn):
    _add_income_transactions(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_income_report(pane)
    assert pane.start_date_edit.date().toPython() == date(2024, 3, 1)
    assert pane.end_date_edit.date().toPython() == date(2024, 3, 15)
    assert pane.range_label.text() == "Showing 2024-03-01 to 2024-03-15"


def test_selecting_income_report_sorts_categories_by_income_descending(qapp, dict_conn):
    _add_income_transactions(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_income_report(pane)

    view = pane.category_table_view
    assert view.model().rowCount() == 2
    assert _table_cell(view, 0, 0) == "Salary"
    assert _table_cell(view, 0, 1) == "1,200.00"
    assert _table_cell(view, 1, 0) == "Freelance"
    assert _table_cell(view, 1, 1) == "300.00"


def test_updating_range_recomputes_income_table_for_narrower_window(qapp, dict_conn):
    _add_income_transactions(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_income_report(pane)

    pane.start_date_edit.setDate(QDate(2024, 3, 10))
    pane.end_date_edit.setDate(QDate(2024, 3, 31))
    pane.update_range_button.click()

    assert pane.range_label.text() == "Showing 2024-03-10 to 2024-03-31"
    view = pane.category_table_view
    assert view.model().rowCount() == 1
    assert _table_cell(view, 0, 0) == "Freelance"
    assert _table_cell(view, 0, 1) == "300.00"


def test_income_report_defaults_to_table_view_with_selector_hidden_elsewhere(qapp, dict_conn):
    _add_income_transactions(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_net_worth_report(pane)
    assert not pane.view_selector.isVisible()

    _select_income_report(pane)
    assert pane.view_selector.isVisible()
    assert pane.view_selector.currentText() == "Table"
    assert pane.category_table_view.isVisible()
    assert not pane.chart_view.isVisible()


def test_switching_income_report_to_pie_chart_shows_chart_and_hides_table(qapp, dict_conn):
    _add_income_transactions(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_income_report(pane)

    pane.view_selector.setCurrentText("Pie Chart")

    assert pane.chart_view.isVisible()
    assert not pane.category_table_view.isVisible()
    series = pane.chart_view.chart().series()[0]
    assert len(series.slices()) == 2
    assert series.slices()[0].label() == "Salary"


def test_selecting_income_report_does_not_disturb_spending_table(qapp, dict_conn):
    _add_income_transactions(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_spending_report(pane)
    assert pane.category_table_view.model().rowCount() == 2

    _select_income_report(pane)
    assert pane.category_table_view.model().rowCount() == 2
    assert _table_cell(pane.category_table_view, 0, 0) == "Salary"

    _select_spending_report(pane)
    assert _table_cell(pane.category_table_view, 0, 0) == "Utilities"


class _FakeCategoryTransactionsDialog:
    last_init_args = None

    def __init__(self, category_name, transactions, parent=None):
        _FakeCategoryTransactionsDialog.last_init_args = (category_name, transactions)

    def exec(self):
        return QDialog.Accepted


def test_double_clicking_category_cell_opens_transactions_dialog(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(
        reports_tab, "CategoryTransactionsDialog", _FakeCategoryTransactionsDialog
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_spending_report(pane)

    pane.category_table_view.doubleClicked.emit(pane.category_table_view.model().index(1, 0))

    category_name, transactions = _FakeCategoryTransactionsDialog.last_init_args
    assert category_name == "Groceries"
    assert [t[0] for t in transactions] == [1000, 1001]


def test_double_clicking_amount_cell_does_not_open_transactions_dialog(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(
        reports_tab, "CategoryTransactionsDialog", _FakeCategoryTransactionsDialog
    )
    _FakeCategoryTransactionsDialog.last_init_args = None
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_spending_report(pane)

    pane.category_table_view.doubleClicked.emit(pane.category_table_view.model().index(1, 1))

    assert _FakeCategoryTransactionsDialog.last_init_args is None


def test_category_table_context_menu_offers_show_transactions_for_spending_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_spending_report(pane)

    labels = [label for label, _callback in pane._category_table_context_actions(1)]
    assert labels == ["Show Transactions"]


def test_show_transactions_action_opens_dialog_for_income_report(qapp, dict_conn, monkeypatch):
    _add_income_transactions(dict_conn)
    monkeypatch.setattr(
        reports_tab, "CategoryTransactionsDialog", _FakeCategoryTransactionsDialog
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_income_report(pane)

    _, callback = pane._category_table_context_actions(0)[0]
    callback()

    category_name, transactions = _FakeCategoryTransactionsDialog.last_init_args
    assert category_name == "Salary"
    assert [t[0] for t in transactions] == [2000]


def test_selecting_investment_report_shows_table_and_hides_chart(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_net_worth_report(pane)
    assert pane.chart_view.isVisible()

    _select_investment_report(pane)
    assert pane.investment_table_view.isVisible()
    assert not pane.chart_view.isVisible()
    assert not pane.category_table_view.isVisible()


def test_investment_report_hides_view_selector_and_custom_categories_button(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_investment_report(pane)
    assert not pane.view_selector_row.isVisible()


def test_selecting_recurring_report_lists_detected_subscriptions(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "_today", lambda: date(2024, 6, 1))
    _add_recurring_transactions(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()

    _select_recurring_report(pane)
    _wait_for_recurring_report(pane)

    assert pane.recurring_table_view.isVisible()
    assert not pane.chart_view.isVisible()
    assert not pane.category_table_view.isVisible()
    assert pane.recurring_table_model.rowCount() == 1
    assert _table_cell(pane.recurring_table_view, 0, 0) == "Store A"
    assert _table_cell(pane.recurring_table_view, 0, 1) == "Checking"
    assert _table_cell(pane.recurring_table_view, 0, 2) == "Monthly"
    assert _table_cell(pane.recurring_table_view, 0, 3) == "3"


def test_recurring_table_view_has_sorting_enabled(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.recurring_table_view.isSortingEnabled()


def test_recurring_report_merges_payees_sharing_a_name_prefix(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "_today", lambda: date(2024, 6, 1))
    dict_conn.execute(
        "INSERT INTO payees VALUES (200, 'VERIZON WIRELESS PAYMENTS 8291'), "
        "(201, 'VERIZON WIRELESS PAYMENTS 7734'), (202, 'VERIZON WIRELESS PAYMENTS 4402')"
    )
    dict_conn.execute(
        "INSERT INTO transactions VALUES "
        "(6000, 1, 20, 200, '2024-01-10', -95.00, NULL, NULL, NULL, NULL, NULL, NULL), "
        "(6001, 1, 20, 201, '2024-02-10', -95.00, NULL, NULL, NULL, NULL, NULL, NULL), "
        "(6002, 1, 20, 202, '2024-03-10', -95.00, NULL, NULL, NULL, NULL, NULL, NULL)"
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()

    _select_recurring_report(pane)
    _wait_for_recurring_report(pane)

    rows = [
        (_table_cell(pane.recurring_table_view, row, 0), _table_cell(pane.recurring_table_view, row, 3))
        for row in range(pane.recurring_table_model.rowCount())
    ]
    merged_rows = [
        row
        for row in rows
        if row[0]
        in (
            "VERIZON WIRELESS PAYMENTS 8291",
            "VERIZON WIRELESS PAYMENTS 7734",
            "VERIZON WIRELESS PAYMENTS 4402",
        )
    ]
    assert merged_rows == [(merged_rows[0][0], "3")]


def test_recurring_report_hides_view_selector_and_custom_categories_button(qapp, dict_conn):
    _add_recurring_transactions(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_recurring_report(pane)
    assert not pane.view_selector_row.isVisible()


def test_selecting_recurring_report_defaults_date_range_to_full_history(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "_today", lambda: date(2024, 6, 1))
    _add_recurring_transactions(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_recurring_report(pane)
    _wait_for_recurring_report(pane)
    assert pane.start_date_edit.date().toPython() == date(2024, 1, 15)
    assert pane.end_date_edit.date().toPython() == date(2024, 3, 15)
    assert pane.range_label.text() == "Showing 2024-01-15 to 2024-03-15"


def test_selecting_recurring_report_defaults_to_three_years_back_when_history_is_older(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(reports_tab, "_today", lambda: date(2026, 8, 30))
    dict_conn.execute(
        "INSERT INTO transactions VALUES "
        "(7000, 1, 20, 100, '2020-01-15', -52.30, 'old charge', NULL, NULL, NULL, NULL, NULL)"
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_recurring_report(pane)
    assert pane.start_date_edit.date().toPython() == date(2023, 8, 30)


def test_recurring_report_busy_indicator_starts_and_stops_during_computation(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "_today", lambda: date(2024, 6, 1))
    _add_recurring_transactions(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    calls = []
    monkeypatch.setattr(pane.recurring_busy_indicator, "start", lambda: calls.append("start"))
    monkeypatch.setattr(pane.recurring_busy_indicator, "stop", lambda: calls.append("stop"))

    _select_recurring_report(pane)
    _wait_for_recurring_report(pane)

    # start() fires twice: once immediately on selection (so the spinner is
    # visible before the synchronous transaction fetch), then again when the
    # background computation kicks off via run_in_background.
    assert calls == ["start", "start", "stop"]
    assert not pane.recurring_status_row.isVisible()


def test_narrowing_recurring_report_range_drops_subscriptions_below_minimum_occurrences(qapp, dict_conn):
    _add_recurring_transactions(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_recurring_report(pane)
    _wait_for_recurring_report(pane)

    pane.start_date_edit.setDate(QDate(2024, 2, 1))
    pane.end_date_edit.setDate(QDate(2024, 3, 31))
    pane.update_range_button.click()
    _wait_for_recurring_report(pane)

    assert pane.recurring_table_model.rowCount() == 0


def test_recurring_report_shows_error_when_no_payee_transactions_exist(qapp, dict_conn):
    errors = []
    pane = ReportsPane(dict_conn, report_error=errors.append, to_usd=lambda cur, amt: amt)
    dict_conn.execute("DELETE FROM transactions")

    _select_recurring_report(pane)

    assert errors
    assert pane.recurring_table_model.rowCount() == 0


def test_selecting_investment_report_defaults_date_range_to_full_history(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_investment_report(pane)
    assert pane.start_date_edit.date().toPython() == date(2024, 1, 10)
    assert pane.end_date_edit.date().toPython() == date(2024, 3, 1)
    assert pane.range_label.text() == "Showing 2024-01-10 to 2024-03-01"


def test_selecting_investment_report_sorts_by_percentage_increase_descending(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_investment_report(pane)

    view = pane.investment_table_view
    assert view.model().rowCount() == 1
    assert _table_cell(view, 0, 0) == "Vanguard Total Stock Market Index"
    assert _table_cell(view, 0, 1) == "+35.94%"
    assert _table_cell(view, 0, 2) == "18.39"
    assert _table_cell(view, 0, 3) == "25.00"
    assert _table_cell(view, 0, 4) == "2024-01-10 to 2024-03-01"


def test_investment_table_supports_clicking_headers_to_sort(qapp, dict_conn):
    dict_conn.execute(
        "INSERT INTO securities VALUES (502, 'Small Cap Fund')"
    )
    dict_conn.execute(
        "INSERT INTO transactions VALUES "
        "(5000, 3, NULL, NULL, '2024-01-10', 100.00, NULL, 502, '1', 1.0, 100.00, NULL), "
        "(5001, 3, NULL, NULL, '2024-02-10', -1.00, NULL, 502, '2', 1.0, 101.00, NULL)"
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_investment_report(pane)

    view = pane.investment_table_view
    assert view.isSortingEnabled()
    assert _table_cell(view, 0, 0) == "Vanguard Total Stock Market Index"

    view.sortByColumn(1, Qt.AscendingOrder)

    assert _table_cell(view, 0, 0) == "Small Cap Fund"
    assert _table_cell(view, 1, 0) == "Vanguard Total Stock Market Index"


def test_updating_investment_range_recomputes_table_for_narrower_window(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_investment_report(pane)

    pane.start_date_edit.setDate(QDate(2024, 1, 10))
    pane.end_date_edit.setDate(QDate(2024, 2, 10))
    pane.update_range_button.click()

    assert pane.range_label.text() == "Showing 2024-01-10 to 2024-02-10"
    view = pane.investment_table_view
    assert view.model().rowCount() == 1
    assert _table_cell(view, 0, 1) == "+17.13%"
    assert _table_cell(view, 0, 3) == "21.54"


def test_updating_investment_range_with_start_after_end_reports_error_and_keeps_table(qapp, dict_conn):
    errors = []
    pane = ReportsPane(dict_conn, report_error=errors.append, to_usd=lambda cur, amt: amt)
    _select_investment_report(pane)

    pane.start_date_edit.setDate(QDate(2024, 3, 1))
    pane.end_date_edit.setDate(QDate(2024, 1, 10))
    pane.update_range_button.click()

    assert errors == ["Start date must be on or before end date."]
    assert pane.range_label.text() == "Showing 2024-01-10 to 2024-03-01"
    assert pane.investment_table_view.model().rowCount() == 1


def test_selecting_investment_report_does_not_disturb_spending_table(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_spending_report(pane)
    assert pane.category_table_view.model().rowCount() == 2

    _select_investment_report(pane)
    assert pane.investment_table_view.model().rowCount() == 1

    _select_spending_report(pane)
    assert _table_cell(pane.category_table_view, 0, 0) == "Utilities"


def _select_projection_report(pane):
    pane.list_view.selectionModel().select(
        pane.list_model.index(4, 0), QItemSelectionModel.ClearAndSelect
    )


def test_reports_list_shows_net_worth_projection_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.rowCount() == len(REPORTS)
    assert pane.list_model.data(pane.list_model.index(4, 0)) == "5. Net Worth Projection"


def test_selecting_projection_report_shows_controls_and_chart_hides_others(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_projection_report(pane)

    assert pane.projection_controls.isVisible()
    assert pane.chart_view.isVisible()
    assert not pane.category_table_view.isVisible()
    assert not pane.investment_table_view.isVisible()
    assert not pane.investment_controls_row.isVisible()
    assert not pane.range_controls_row.isVisible()
    assert not pane.range_label.isVisible()


def test_projection_controls_are_hosted_in_a_scroll_area(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    assert isinstance(pane.projection_controls_scroll_area, QScrollArea)
    assert pane.projection_controls_scroll_area.widget() is pane.projection_controls
    assert pane.projection_controls_scroll_area.widgetResizable() is True


def test_chart_and_projection_scroll_area_share_the_layout_equally(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    layout = pane.chart_view.parentWidget().layout()
    chart_stretch = layout.stretch(layout.indexOf(pane.chart_view))
    scroll_stretch = layout.stretch(layout.indexOf(pane.projection_controls_scroll_area))

    assert chart_stretch == scroll_stretch == 1
    assert pane.projection_controls_scroll_area.sizePolicy().verticalPolicy() == QSizePolicy.Ignored


def test_selecting_projection_report_shows_scroll_area_and_hides_on_switch(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()

    _select_projection_report(pane)
    assert pane.projection_controls_scroll_area.isVisible()

    _select_net_worth_report(pane)
    assert not pane.projection_controls_scroll_area.isVisible()


def test_selecting_other_report_after_projection_restores_range_controls(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_projection_report(pane)
    _select_net_worth_report(pane)

    assert not pane.projection_controls.isVisible()
    assert pane.range_controls_row.isVisible()
    assert pane.range_label.isVisible()


def test_selecting_projection_report_autofills_starting_investment_value(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_projection_report(pane)

    assert pane.projection_controls.starting_investment_value_spinbox.value() == pytest.approx(426.30)


def test_selecting_projection_report_loads_persisted_settings(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(
        reports_tab,
        "load_projection_profiles",
        lambda: (DEFAULT_PROFILE_NAME, {DEFAULT_PROFILE_NAME: {"retirement_age": 70, "annual_income": 12345.0}}),
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_projection_report(pane)

    assert pane.projection_controls.retirement_age_spinbox.value() == 70
    assert pane.projection_controls.annual_income_spinbox.value() == pytest.approx(12345.0)


def test_selecting_projection_report_renders_stacked_assets_and_investments_bands(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_projection_report(pane)

    chart = pane.chart_view.chart()
    series = [s for s in chart.series() if s.name()]
    assert [s.name() for s in series] == ["Assets", "Investments"]
    assets_series, investments_series = series
    assert assets_series.upperSeries().count() > 1
    # dict_conn has no Asset accounts, so the Assets band is flat at 0 and
    # the Investments band's top edge equals the investment-only total.
    assert assets_series.upperSeries().at(0).y() == pytest.approx(0.0)
    assert investments_series.upperSeries().at(0).y() == pytest.approx(426.30)


def test_selecting_projection_report_includes_asset_accounts_in_the_starting_total(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    dict_conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES (5, 'House', '3', FALSE, 300000.00, 'USD', NULL)"
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_projection_report(pane)

    chart = pane.chart_view.chart()
    assets_series, investments_series = [s for s in chart.series() if s.name()]
    assert assets_series.upperSeries().at(0).y() == pytest.approx(300000.00)
    assert investments_series.upperSeries().at(0).y() == pytest.approx(300426.30)


def test_selecting_projection_report_populates_house_account_choices(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    dict_conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES (5, 'House', '3', FALSE, 300000.00, 'USD', NULL)"
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_projection_report(pane)

    combo = pane.projection_controls.house_account_combo
    assert [combo.itemText(i) for i in range(combo.count())] == ["None", "House"]


def test_selling_the_house_moves_its_value_from_assets_to_investments_without_double_counting(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    dict_conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES (5, 'House', '3', FALSE, 300000.00, 'USD', NULL)"
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    controls = pane.projection_controls
    controls.return_rate_before_spinbox.setValue(0.0)
    controls.return_rate_after_spinbox.setValue(0.0)
    controls.annual_income_spinbox.setValue(0.0)
    controls.spending_before_spinbox.setValue(0.0)
    controls.spending_after_spinbox.setValue(0.0)
    controls.social_security_amount_spinbox.setValue(0.0)
    controls.retirement_age_spinbox.setValue(100)
    controls.house_account_combo.setCurrentIndex(1)
    controls.house_sale_year_spinbox.setValue(date.today().year + 1)
    controls.update_button.click()

    # The house's value leaves the Assets band and lands in Investments'
    # own contribution in the same year, so the combined total (the top of
    # the Investments band) stays flat across the sale rather than jumping.
    total_series = pane.chart_view.chart().series()[1].upperSeries()
    assert total_series.at(1).y() == pytest.approx(total_series.at(0).y())


def test_selecting_house_account_removes_its_value_from_assets_in_the_sale_year(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    dict_conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES (5, 'House', '3', FALSE, 300000.00, 'USD', NULL)"
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    controls = pane.projection_controls
    controls.house_account_combo.setCurrentIndex(1)
    controls.house_sale_year_spinbox.setValue(date.today().year + 1)
    controls.update_button.click()

    assets_series = pane.chart_view.chart().series()[0].upperSeries()
    assert assets_series.at(0).y() == pytest.approx(300000.00)
    assert assets_series.at(1).y() == pytest.approx(0.0)


def test_house_sale_tax_is_applied_only_to_the_gain_over_purchase_price(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    dict_conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES (5, 'House', '3', FALSE, 300000.00, 'USD', NULL)"
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    controls = pane.projection_controls
    controls.return_rate_before_spinbox.setValue(0.0)
    controls.return_rate_after_spinbox.setValue(0.0)
    controls.annual_income_spinbox.setValue(0.0)
    controls.spending_before_spinbox.setValue(0.0)
    controls.spending_after_spinbox.setValue(0.0)
    controls.social_security_amount_spinbox.setValue(0.0)
    controls.retirement_age_spinbox.setValue(100)
    controls.house_account_combo.setCurrentIndex(1)
    controls.house_sale_year_spinbox.setValue(date.today().year + 1)
    controls.house_purchase_price_spinbox.setValue(100000.0)
    controls.house_sale_tax_rate_spinbox.setValue(20.0)
    controls.update_button.click()

    # Gain is 300000 - 100000 = 200000, taxed at 20% = 40000, so only
    # 260000 of the house's 300000 value actually lands in Investments.
    total_series = pane.chart_view.chart().series()[1].upperSeries()
    assert total_series.at(1).y() == pytest.approx(total_series.at(0).y() - 40000.0)


def test_house_sale_tax_does_not_apply_to_a_loss(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    dict_conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES (5, 'House', '3', FALSE, 300000.00, 'USD', NULL)"
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    controls = pane.projection_controls
    controls.return_rate_before_spinbox.setValue(0.0)
    controls.return_rate_after_spinbox.setValue(0.0)
    controls.annual_income_spinbox.setValue(0.0)
    controls.spending_before_spinbox.setValue(0.0)
    controls.spending_after_spinbox.setValue(0.0)
    controls.social_security_amount_spinbox.setValue(0.0)
    controls.retirement_age_spinbox.setValue(100)
    controls.house_account_combo.setCurrentIndex(1)
    controls.house_sale_year_spinbox.setValue(date.today().year + 1)
    controls.house_purchase_price_spinbox.setValue(400000.0)
    controls.house_sale_tax_rate_spinbox.setValue(20.0)
    controls.update_button.click()

    # House value (300000) is below purchase price (400000): no gain, so
    # the full house value still lands in Investments untaxed.
    total_series = pane.chart_view.chart().series()[1].upperSeries()
    assert total_series.at(1).y() == pytest.approx(total_series.at(0).y())


def test_unchecking_include_house_sale_keeps_house_in_assets_and_out_of_cash_flow(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    dict_conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES (5, 'House', '3', FALSE, 300000.00, 'USD', NULL)"
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    controls = pane.projection_controls
    controls.return_rate_before_spinbox.setValue(0.0)
    controls.return_rate_after_spinbox.setValue(0.0)
    controls.annual_income_spinbox.setValue(0.0)
    controls.spending_before_spinbox.setValue(0.0)
    controls.spending_after_spinbox.setValue(0.0)
    controls.social_security_amount_spinbox.setValue(0.0)
    controls.retirement_age_spinbox.setValue(100)
    controls.house_account_combo.setCurrentIndex(1)
    controls.house_sale_year_spinbox.setValue(date.today().year + 1)
    controls.include_house_sale_checkbox.setChecked(False)
    controls.update_button.click()

    assets_series = pane.chart_view.chart().series()[0].upperSeries()
    investments_series = pane.chart_view.chart().series()[1].upperSeries()
    assert assets_series.at(1).y() == pytest.approx(assets_series.at(0).y())
    assert investments_series.at(1).y() == pytest.approx(investments_series.at(0).y())


def test_inheritance_adds_lump_sum_to_projected_cash_flow(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    controls = pane.projection_controls
    controls.return_rate_before_spinbox.setValue(0.0)
    controls.return_rate_after_spinbox.setValue(0.0)
    controls.annual_income_spinbox.setValue(0.0)
    controls.spending_before_spinbox.setValue(0.0)
    controls.spending_after_spinbox.setValue(0.0)
    controls.social_security_amount_spinbox.setValue(0.0)
    controls.retirement_age_spinbox.setValue(100)
    controls.inheritance_amount_spinbox.setValue(5000.0)
    controls.inheritance_year_spinbox.setValue(date.today().year + 1)
    controls.update_button.click()

    investments_series = pane.chart_view.chart().series()[1].upperSeries()
    assert investments_series.at(1).y() == pytest.approx(investments_series.at(0).y() + 5000.0)


def test_unchecking_include_inheritance_excludes_it_from_projected_cash_flow(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    controls = pane.projection_controls
    controls.return_rate_before_spinbox.setValue(0.0)
    controls.return_rate_after_spinbox.setValue(0.0)
    controls.annual_income_spinbox.setValue(0.0)
    controls.spending_before_spinbox.setValue(0.0)
    controls.spending_after_spinbox.setValue(0.0)
    controls.social_security_amount_spinbox.setValue(0.0)
    controls.retirement_age_spinbox.setValue(100)
    controls.inheritance_amount_spinbox.setValue(5000.0)
    controls.inheritance_year_spinbox.setValue(date.today().year + 1)
    controls.include_inheritance_checkbox.setChecked(False)
    controls.update_button.click()

    investments_series = pane.chart_view.chart().series()[1].upperSeries()
    assert investments_series.at(1).y() == pytest.approx(investments_series.at(0).y())


def test_second_social_security_person_adds_to_projected_cash_flow(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    controls = pane.projection_controls
    controls.return_rate_before_spinbox.setValue(0.0)
    controls.return_rate_after_spinbox.setValue(0.0)
    controls.annual_income_spinbox.setValue(0.0)
    controls.spending_before_spinbox.setValue(0.0)
    controls.spending_after_spinbox.setValue(0.0)
    controls.tax_rate_spinbox.setValue(0.0)
    controls.inflation_rate_spinbox.setValue(0.0)
    controls.retirement_age_spinbox.setValue(100)
    controls.social_security_amount_spinbox.setValue(0.0)
    controls.social_security_amount_2_spinbox.setValue(1000.0)
    controls.social_security_start_year_2_spinbox.setValue(date.today().year + 1)
    controls.update_button.click()

    investments_series = pane.chart_view.chart().series()[1].upperSeries()
    assert investments_series.at(1).y() == pytest.approx(investments_series.at(0).y() + 1000.0)


def test_rsu_vesting_forecast_adds_after_tax_vest_value_to_projected_cash_flow(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    next_year = date.today().year + 1
    dict_conn.execute(
        "INSERT INTO transactions VALUES "
        f"(3500, 3, NULL, NULL, '{next_year}-06-15', 0.00, NULL, 500, '18', 5.0, NULL, NULL)"
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    controls = pane.projection_controls
    controls.return_rate_before_spinbox.setValue(0.0)
    controls.return_rate_after_spinbox.setValue(0.0)
    controls.annual_income_spinbox.setValue(0.0)
    controls.spending_before_spinbox.setValue(0.0)
    controls.spending_after_spinbox.setValue(0.0)
    controls.tax_rate_spinbox.setValue(0.0)
    controls.inflation_rate_spinbox.setValue(0.0)
    controls.social_security_amount_spinbox.setValue(0.0)
    controls.retirement_age_spinbox.setValue(100)
    controls.update_button.click()

    # Brokerage A / security 500's latest known price is 22.63 (the
    # 2024-03-01 sell); 5 shares at that price, taxed at the default 35%,
    # nets 113.15 * 0.65 = 73.5475.
    investments_series = pane.chart_view.chart().series()[1].upperSeries()
    assert investments_series.at(1).y() == pytest.approx(investments_series.at(0).y() + 73.5475)


def test_unchecking_include_rsu_vesting_excludes_it_from_projected_cash_flow(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    next_year = date.today().year + 1
    dict_conn.execute(
        "INSERT INTO transactions VALUES "
        f"(3500, 3, NULL, NULL, '{next_year}-06-15', 0.00, NULL, 500, '18', 5.0, NULL, NULL)"
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    controls = pane.projection_controls
    controls.return_rate_before_spinbox.setValue(0.0)
    controls.return_rate_after_spinbox.setValue(0.0)
    controls.annual_income_spinbox.setValue(0.0)
    controls.spending_before_spinbox.setValue(0.0)
    controls.spending_after_spinbox.setValue(0.0)
    controls.tax_rate_spinbox.setValue(0.0)
    controls.inflation_rate_spinbox.setValue(0.0)
    controls.social_security_amount_spinbox.setValue(0.0)
    controls.retirement_age_spinbox.setValue(100)
    controls.include_rsu_vesting_checkbox.setChecked(False)
    controls.update_button.click()

    investments_series = pane.chart_view.chart().series()[1].upperSeries()
    assert investments_series.at(1).y() == pytest.approx(investments_series.at(0).y())


def test_college_tuition_projection_reduces_projected_cash_flow_when_tuition_is_paid(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    tuition_year = date.today().year + 1
    monkeypatch.setattr(
        reports_tab,
        "load_college_tuition_settings",
        lambda: {
            "selected_account_ids": [3],
            "annual_return_rate": 0.0,
            "contribution_per_quarter": 0.0,
            "contribution_end_year": date.today().year,
            "person1_start_year": tuition_year,
            "person1_end_year": tuition_year,
            "person1_tuition_per_quarter": 1000.0,
            "person1_housing_per_quarter": 0.0,
            "person2_start_year": date.today().year,
            "person2_end_year": date.today().year - 1,
            "person2_tuition_per_quarter": 0.0,
            "person2_housing_per_quarter": 0.0,
        },
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    controls = pane.projection_controls
    controls.return_rate_before_spinbox.setValue(0.0)
    controls.return_rate_after_spinbox.setValue(0.0)
    controls.annual_income_spinbox.setValue(0.0)
    controls.spending_before_spinbox.setValue(0.0)
    controls.spending_after_spinbox.setValue(0.0)
    controls.tax_rate_spinbox.setValue(0.0)
    controls.inflation_rate_spinbox.setValue(0.0)
    controls.social_security_amount_spinbox.setValue(0.0)
    controls.retirement_age_spinbox.setValue(100)
    controls.update_button.click()

    # $1000/quarter tuition for all 4 quarters of tuition_year = $4000.
    investments_series = pane.chart_view.chart().series()[1].upperSeries()
    assert investments_series.at(1).y() == pytest.approx(investments_series.at(0).y() - 4000.0)


def test_unchecking_include_college_tuition_excludes_it_from_projected_cash_flow(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    tuition_year = date.today().year + 1
    monkeypatch.setattr(
        reports_tab,
        "load_college_tuition_settings",
        lambda: {
            "selected_account_ids": [3],
            "annual_return_rate": 0.0,
            "contribution_per_quarter": 0.0,
            "contribution_end_year": date.today().year,
            "person1_start_year": tuition_year,
            "person1_end_year": tuition_year,
            "person1_tuition_per_quarter": 1000.0,
            "person1_housing_per_quarter": 0.0,
            "person2_start_year": date.today().year,
            "person2_end_year": date.today().year - 1,
            "person2_tuition_per_quarter": 0.0,
            "person2_housing_per_quarter": 0.0,
        },
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    controls = pane.projection_controls
    controls.return_rate_before_spinbox.setValue(0.0)
    controls.return_rate_after_spinbox.setValue(0.0)
    controls.annual_income_spinbox.setValue(0.0)
    controls.spending_before_spinbox.setValue(0.0)
    controls.spending_after_spinbox.setValue(0.0)
    controls.tax_rate_spinbox.setValue(0.0)
    controls.inflation_rate_spinbox.setValue(0.0)
    controls.social_security_amount_spinbox.setValue(0.0)
    controls.retirement_age_spinbox.setValue(100)
    controls.include_college_tuition_checkbox.setChecked(False)
    controls.update_button.click()

    investments_series = pane.chart_view.chart().series()[1].upperSeries()
    assert investments_series.at(1).y() == pytest.approx(investments_series.at(0).y())


def test_clicking_update_in_projection_panel_saves_settings_and_rerenders(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    saved = {}

    def fake_save(profiles, active_profile):
        saved["profiles"] = profiles
        saved["active_profile"] = active_profile

    monkeypatch.setattr(reports_tab, "save_projection_profiles", fake_save)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    pane.projection_controls.retirement_age_spinbox.setValue(70)
    pane.projection_controls.update_button.click()

    assert saved["active_profile"] == DEFAULT_PROFILE_NAME
    assert saved["profiles"][DEFAULT_PROFILE_NAME]["retirement_age"] == 70
    assert "starting_investment_value" not in saved["profiles"][DEFAULT_PROFILE_NAME]


def test_persisted_settings_round_trip_through_panel(qapp, dict_conn, monkeypatch, tmp_path):
    settings_path = tmp_path / "projection_settings.json"
    dict_conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES (5, 'House', '3', FALSE, 300000.00, 'USD', NULL)"
    )
    monkeypatch.setattr(
        reports_tab, "load_projection_profiles",
        functools.partial(_real_load_projection_profiles, path=settings_path),
    )
    monkeypatch.setattr(
        reports_tab, "save_projection_profiles",
        functools.partial(_real_save_projection_profiles, path=settings_path),
    )

    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)
    pane.projection_controls.retirement_age_spinbox.setValue(70)
    pane.projection_controls.house_account_combo.setCurrentIndex(1)
    pane.projection_controls.update_button.click()

    pane2 = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    monkeypatch.setattr(
        reports_tab, "load_projection_profiles",
        functools.partial(_real_load_projection_profiles, path=settings_path),
    )
    _select_projection_report(pane2)

    assert pane2.projection_controls.retirement_age_spinbox.value() == 70
    assert pane2.projection_controls.house_account_combo.currentData() == 5


def test_switching_projection_profile_saves_current_and_loads_selected(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(
        reports_tab,
        "load_projection_profiles",
        lambda: (
            DEFAULT_PROFILE_NAME,
            {DEFAULT_PROFILE_NAME: {}, "Retire Early": {"retirement_age": 50}},
        ),
    )
    saved = {}
    monkeypatch.setattr(
        reports_tab,
        "save_projection_profiles",
        lambda profiles, active_profile: saved.update(profiles=profiles, active_profile=active_profile),
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)
    pane.projection_controls.retirement_age_spinbox.setValue(80)

    pane.projection_controls.profile_combo.setCurrentText("Retire Early")

    assert pane.projection_controls.retirement_age_spinbox.value() == 50
    assert saved["active_profile"] == "Retire Early"
    assert saved["profiles"][DEFAULT_PROFILE_NAME]["retirement_age"] == 80


def test_toggling_compare_mode_plots_one_line_per_profile_without_assets_band(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(
        reports_tab,
        "load_projection_profiles",
        lambda: (
            DEFAULT_PROFILE_NAME,
            {DEFAULT_PROFILE_NAME: {}, "Retire Early": {"retirement_age": 50}},
        ),
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    pane.projection_controls.compare_all_button.click()

    chart = pane.chart_view.chart()
    series_names = {s.name() for s in chart.series() if s.name()}
    assert series_names == {DEFAULT_PROFILE_NAME, "Retire Early"}


def test_toggling_compare_mode_off_restores_stacked_bands(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    pane.projection_controls.compare_all_button.click()
    pane.projection_controls.compare_all_button.click()

    chart = pane.chart_view.chart()
    series_names = [s.name() for s in chart.series() if s.name()]
    assert series_names == ["Assets", "Investments"]


def test_toggling_compare_mode_saves_unsaved_edits_to_active_profile_first(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(
        reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {DEFAULT_PROFILE_NAME: {}})
    )
    saved = {}
    monkeypatch.setattr(
        reports_tab,
        "save_projection_profiles",
        lambda profiles, active_profile: saved.update(profiles=profiles, active_profile=active_profile),
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)
    pane.projection_controls.retirement_age_spinbox.setValue(50)

    pane.projection_controls.compare_all_button.click()

    assert saved["profiles"][DEFAULT_PROFILE_NAME]["retirement_age"] == 50


def test_checking_table_view_swaps_chart_for_a_table_of_the_yearly_rows(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_projection_report(pane)

    pane.projection_controls.table_view_checkbox.click()

    assert not pane.chart_view.isVisible()
    assert pane.projection_table_view.isVisible()
    assert pane.projection_table_model.rowCount() > 0
    assert _table_cell(pane.projection_table_view, 0, 0) == str(date.today().year)


def test_unchecking_table_view_restores_the_chart(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_projection_report(pane)

    pane.projection_controls.table_view_checkbox.click()
    pane.projection_controls.table_view_checkbox.click()

    assert pane.chart_view.isVisible()
    assert not pane.projection_table_view.isVisible()


def test_investment_income_column_isolates_growth_and_net_cash_flow_is_the_total_change(
    qapp, dict_conn, monkeypatch
):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_projection_report(pane)

    controls = pane.projection_controls
    controls.return_rate_before_spinbox.setValue(10.0)
    controls.annual_income_spinbox.setValue(0.0)
    controls.spending_before_spinbox.setValue(0.0)
    controls.social_security_amount_spinbox.setValue(0.0)
    controls.retirement_age_spinbox.setValue(100)
    controls.include_rsu_vesting_checkbox.setChecked(False)
    controls.include_college_tuition_checkbox.setChecked(False)
    controls.include_house_sale_checkbox.setChecked(False)
    controls.include_inheritance_checkbox.setChecked(False)
    controls.update_button.click()
    controls.table_view_checkbox.click()

    def cell(row, col):
        return float(_table_cell(pane.projection_table_view, row, col).replace(",", ""))

    # With no income/spending/lump sums, net worth only moves via 10% growth,
    # so Net Cash Flow (the total year-over-year change) should equal
    # Investment Income exactly, and match 10% of the prior year's total.
    row0_net_worth = cell(0, 13)
    row1_investment_income = cell(1, 9)
    row1_net_cash_flow = cell(1, 10)
    row1_net_worth = cell(1, 13)

    assert row1_net_cash_flow == pytest.approx(row1_net_worth - row0_net_worth)
    assert row1_investment_income == pytest.approx(row1_net_cash_flow)
    assert row1_investment_income == pytest.approx(row0_net_worth * 0.10)


def test_projection_table_reflects_active_profile_even_in_compare_mode(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(
        reports_tab,
        "load_projection_profiles",
        lambda: (
            DEFAULT_PROFILE_NAME,
            {DEFAULT_PROFILE_NAME: {}, "Retire Early": {"retirement_age": 50}},
        ),
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_projection_report(pane)

    pane.projection_controls.compare_all_button.click()
    pane.projection_controls.table_view_checkbox.click()

    assert pane.projection_table_view.isVisible()
    assert pane.projection_table_model.rowCount() > 0


def test_selecting_other_report_after_table_view_hides_the_projection_table(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_projection_report(pane)
    pane.projection_controls.table_view_checkbox.click()

    _select_net_worth_report(pane)

    assert not pane.projection_table_view.isVisible()


def test_updating_projection_refreshes_the_table_while_it_is_hidden(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_projection_report(pane)

    pane.projection_controls.retirement_age_spinbox.setValue(50)
    pane.projection_controls.update_button.click()

    assert pane.projection_table_model.rowCount() > 0


def test_renaming_projection_profile_persists_the_new_name(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    saved = {}
    monkeypatch.setattr(
        reports_tab,
        "save_projection_profiles",
        lambda profiles, active_profile: saved.update(profiles=profiles, active_profile=active_profile),
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    pane.projection_controls.profile_name_edit.setText("My Plan")
    pane.projection_controls.profile_name_edit.editingFinished.emit()

    assert saved["active_profile"] == "My Plan"
    assert "My Plan" in saved["profiles"]
    assert DEFAULT_PROFILE_NAME not in saved["profiles"]


def test_adding_projection_profile_seeds_from_current_and_switches(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_profiles", lambda: (DEFAULT_PROFILE_NAME, {}))
    monkeypatch.setattr("projection_controls.QInputDialog.getText", lambda *a, **k: ("Retire Early", True))
    saved = {}
    monkeypatch.setattr(
        reports_tab,
        "save_projection_profiles",
        lambda profiles, active_profile: saved.update(profiles=profiles, active_profile=active_profile),
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)
    pane.projection_controls.retirement_age_spinbox.setValue(58)

    pane.projection_controls.add_profile_button.click()

    assert pane.projection_controls.profile_combo.currentText() == "Retire Early"
    assert pane.projection_controls.retirement_age_spinbox.value() == 58
    assert saved["active_profile"] == "Retire Early"
    assert saved["profiles"]["Retire Early"]["retirement_age"] == 58
    assert saved["profiles"][DEFAULT_PROFILE_NAME]["retirement_age"] == 58


def test_reports_list_shows_college_tuition_projection_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.rowCount() == len(REPORTS)
    assert pane.list_model.data(pane.list_model.index(5, 0)) == "6. College Tuition Projection"


def test_selecting_college_tuition_report_shows_controls_and_chart_hides_others(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_college_tuition_report(pane)

    assert pane.college_tuition_controls_scroll_area.isVisible()
    assert pane.chart_view.isVisible()
    assert not pane.category_table_view.isVisible()
    assert not pane.investment_table_view.isVisible()
    assert not pane.investment_controls_row.isVisible()
    assert not pane.range_controls_row.isVisible()
    assert not pane.range_label.isVisible()


def test_selecting_other_report_after_college_tuition_hides_its_controls(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_college_tuition_report(pane)
    _select_net_worth_report(pane)

    assert not pane.college_tuition_controls_scroll_area.isVisible()
    assert pane.range_controls_row.isVisible()
    assert pane.range_label.isVisible()


def test_selecting_college_tuition_report_autofills_starting_fund_value(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_college_tuition_settings", lambda: {})
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_college_tuition_report(pane)

    assert pane.college_tuition_controls.starting_fund_value_spinbox.value() == pytest.approx(426.30)


def test_selecting_college_tuition_report_loads_persisted_settings(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(
        reports_tab, "load_college_tuition_settings",
        lambda: {"contribution_end_year": 2050, "annual_return_rate": 4.5},
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_college_tuition_report(pane)

    assert pane.college_tuition_controls.contribution_end_year_spinbox.value() == 2050
    assert pane.college_tuition_controls.annual_return_rate_spinbox.value() == pytest.approx(4.5)


def test_selecting_college_tuition_report_renders_a_fund_balance_line_series(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_college_tuition_settings", lambda: {})
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_college_tuition_report(pane)

    chart = pane.chart_view.chart()
    series = chart.series()
    assert [s.name() for s in series if s.name()] == ["College Fund Balance"]
    fund_series = series[0]
    assert fund_series.count() > 1
    assert fund_series.at(0).y() == pytest.approx(426.30)


def test_clicking_update_in_college_tuition_panel_rerenders_chart_from_new_inputs(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_college_tuition_settings", lambda: {})
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_college_tuition_report(pane)

    controls = pane.college_tuition_controls
    controls.annual_return_rate_spinbox.setValue(0.0)
    controls.contribution_per_quarter_spinbox.setValue(0.0)

    today = date.today()
    start_year = today.year + 5
    tuition_per_quarter = 1000.0
    housing_per_quarter = 500.0
    controls.person1_start_year_spinbox.setValue(start_year)
    controls.person1_end_year_spinbox.setValue(start_year)
    controls.person1_tuition_per_quarter_spinbox.setValue(tuition_per_quarter)
    controls.person1_housing_per_quarter_spinbox.setValue(housing_per_quarter)

    # start_year after end_year keeps person2 out of every quarter of the projection.
    controls.person2_start_year_spinbox.setValue(2200)
    controls.person2_end_year_spinbox.setValue(1900)
    controls.person2_tuition_per_quarter_spinbox.setValue(0.0)
    controls.person2_housing_per_quarter_spinbox.setValue(0.0)

    controls.update_button.click()

    current_quarter = (today.month - 1) // 3 + 1
    # Row indices are a straight quarter count from (today.year, current_quarter);
    # mirrors the indexing compute_college_tuition_projection itself uses.
    index_before_active_year = (start_year - 1 - today.year) * 4 + (4 - current_quarter)
    index_end_of_active_year = (start_year - today.year) * 4 + (4 - current_quarter)

    fund_series = pane.chart_view.chart().series()[0]
    before_value = fund_series.at(index_before_active_year).y()
    end_value = fund_series.at(index_end_of_active_year).y()

    assert end_value == pytest.approx(
        before_value - 4 * (tuition_per_quarter + housing_per_quarter)
    )


def test_clicking_update_in_college_tuition_panel_saves_settings_and_rerenders(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_college_tuition_settings", lambda: {})
    saved = {}
    monkeypatch.setattr(reports_tab, "save_college_tuition_settings", saved.update)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_college_tuition_report(pane)

    pane.college_tuition_controls.contribution_end_year_spinbox.setValue(2050)
    pane.college_tuition_controls.update_button.click()

    assert saved["contribution_end_year"] == 2050
    assert "starting_fund_value" not in saved


def test_persisted_settings_round_trip_through_college_tuition_panel(qapp, dict_conn, monkeypatch, tmp_path):
    settings_path = tmp_path / "college_tuition_settings.json"
    monkeypatch.setattr(
        reports_tab, "load_college_tuition_settings",
        functools.partial(_real_load_college_tuition_settings, path=settings_path),
    )
    monkeypatch.setattr(
        reports_tab, "save_college_tuition_settings",
        functools.partial(_real_save_college_tuition_settings, path=settings_path),
    )

    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_college_tuition_report(pane)
    pane.college_tuition_controls.contribution_end_year_spinbox.setValue(2050)
    pane.college_tuition_controls.set_values({"selected_account_ids": [3]})
    pane.college_tuition_controls.update_button.click()

    pane2 = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    monkeypatch.setattr(
        reports_tab, "load_college_tuition_settings",
        functools.partial(_real_load_college_tuition_settings, path=settings_path),
    )
    _select_college_tuition_report(pane2)

    assert pane2.college_tuition_controls.contribution_end_year_spinbox.value() == 2050
    assert pane2.college_tuition_controls.values()["selected_account_ids"] == [3]


def _select_assets_and_investments_report(pane):
    pane.list_view.selectionModel().select(
        pane.list_model.index(6, 0), QItemSelectionModel.ClearAndSelect
    )


def _add_asset_and_loan_accounts(conn):
    conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES "
        "(5, 'House', '3', FALSE, 500000.00, 'USD', NULL), "
        "(6, 'Car Loan', '6', FALSE, -15000.00, 'USD', NULL)"
    )


def test_reports_list_shows_assets_and_investments_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.rowCount() == len(REPORTS)
    assert pane.list_model.data(pane.list_model.index(6, 0)) == "7. Assets and investments"


def test_selecting_assets_and_investments_report_shows_table_hides_others(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_net_worth_report(pane)
    assert pane.chart_view.isVisible()

    _select_assets_and_investments_report(pane)
    assert pane.assets_investments_table_view.isVisible()
    assert not pane.assets_investments_bar_chart_view.isVisible()
    assert not pane.assets_investments_pies_panel.isVisible()
    assert not pane.chart_view.isVisible()
    assert not pane.category_table_view.isVisible()
    assert not pane.investment_table_view.isVisible()
    assert not pane.investment_controls_row.isVisible()
    assert not pane.range_controls_row.isVisible()
    assert not pane.range_label.isVisible()


def test_assets_and_investments_view_selector_shows_table_bar_and_pie_options(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_assets_and_investments_report(pane)

    assert pane.view_selector_row.isVisible()
    assert not pane.custom_categories_button.isVisible()
    assert pane.view_selector.currentText() == "Table"
    options = [pane.view_selector.itemText(i) for i in range(pane.view_selector.count())]
    assert options == ["Table", "Bar Chart", "Pie Charts"]


def test_switching_assets_and_investments_to_bar_chart_stacks_accounts_per_section(qapp, dict_conn):
    _add_asset_and_loan_accounts(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_assets_and_investments_report(pane)

    pane.view_selector.setCurrentText("Bar Chart")

    assert pane.assets_investments_bar_chart_view.isVisible()
    assert not pane.assets_investments_table_view.isVisible()
    series = pane.assets_investments_bar_chart_view.chart().series()[0]
    labels = sorted(bar_set.label() for bar_set in series.barSets())
    assert labels == ["Brokerage A", "Brokerage B", "Car Loan", "House"]


def test_switching_assets_and_investments_to_pie_charts_shows_one_pie_per_section(qapp, dict_conn):
    _add_asset_and_loan_accounts(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_assets_and_investments_report(pane)

    pane.view_selector.setCurrentText("Pie Charts")

    assert pane.assets_investments_pies_panel.isVisible()
    assert not pane.assets_investments_table_view.isVisible()
    investments_pie = pane.assets_investments_pie_charts["Investments"].chart().series()[0]
    assert sorted(pie_slice.label() for pie_slice in investments_pie.slices()) == [
        "Brokerage A",
        "Brokerage B",
    ]
    assets_pie = pane.assets_investments_pie_charts["Assets"].chart().series()[0]
    assert [pie_slice.label() for pie_slice in assets_pie.slices()] == ["House"]
    loans_pie = pane.assets_investments_pie_charts["Loans / Liabilities"].chart().series()[0]
    assert [pie_slice.label() for pie_slice in loans_pie.slices()] == ["Car Loan"]


def test_switching_assets_and_investments_back_to_table_hides_charts(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_assets_and_investments_report(pane)
    pane.view_selector.setCurrentText("Bar Chart")

    pane.view_selector.setCurrentText("Table")

    assert pane.assets_investments_table_view.isVisible()
    assert not pane.assets_investments_bar_chart_view.isVisible()
    assert not pane.assets_investments_pies_panel.isVisible()


def test_assets_and_investments_report_lists_accounts_by_section_with_totals(qapp, dict_conn):
    _add_asset_and_loan_accounts(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_assets_and_investments_report(pane)

    view = pane.assets_investments_table_view
    rows = [
        (_table_cell(view, row, 0), _table_cell(view, row, 1), _table_cell(view, row, 2))
        for row in range(view.model().rowCount())
    ]
    assert rows == [
        ("Investments", "", ""),
        ("", "Brokerage A", "226.30"),
        ("", "Brokerage B", "200.00"),
        ("", "Total Investments", "426.30"),
        ("Assets", "", ""),
        ("", "House", "500,000.00"),
        ("", "Total Assets", "500,000.00"),
        ("Loans / Liabilities", "", ""),
        ("", "Car Loan", "15,000.00"),
        ("", "Total Loans", "15,000.00"),
        ("", "Total Balance", "485,426.30"),
    ]


def test_assets_and_investments_report_has_account_type_column(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_assets_and_investments_report(pane)

    model = pane.assets_investments_table_model
    assert model.headerData(0, Qt.Horizontal) == "Account Type"
    assert model.headerData(1, Qt.Horizontal) == "Account"
    assert model.headerData(2, Qt.Horizontal) == "Value (USD)"


def test_assets_and_investments_report_bolds_headers_and_totals(qapp, dict_conn):
    _add_asset_and_loan_accounts(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_assets_and_investments_report(pane)

    model = pane.assets_investments_table_model
    assert model.data(model.index(0, 0), Qt.FontRole).bold()
    assert model.data(model.index(3, 0), Qt.FontRole).bold()
    assert model.data(model.index(1, 0), Qt.FontRole) is None


def test_assets_and_investments_report_omits_closed_accounts(qapp, dict_conn):
    _add_asset_and_loan_accounts(dict_conn)
    dict_conn.execute("UPDATE accounts SET is_closed = TRUE WHERE account_id = 6")
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_assets_and_investments_report(pane)

    view = pane.assets_investments_table_view
    labels = [_table_cell(view, row, 1) for row in range(view.model().rowCount())]
    assert "Car Loan" not in labels
    assert "Total Loans" in labels


def test_selecting_other_report_after_assets_and_investments_hides_its_table(qapp, dict_conn):
    _add_asset_and_loan_accounts(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_assets_and_investments_report(pane)
    _select_net_worth_report(pane)

    assert not pane.assets_investments_table_view.isVisible()
    assert pane.range_controls_row.isVisible()
    assert pane.range_label.isVisible()


def _select_rsu_vesting_forecast_report(pane):
    pane.list_view.selectionModel().select(
        pane.list_model.index(8, 0), QItemSelectionModel.ClearAndSelect
    )


def _add_future_vest(conn):
    # Brokerage A / security 500 already has priced Buy/Buy/Sell trades in
    # dict_conn, so its latest known price (22.63, from the 2024-03-01 sell)
    # is what the forecast should use for this future vest's estimated value.
    conn.execute(
        "INSERT INTO transactions VALUES "
        "(3500, 3, NULL, NULL, '2099-06-15', 0.00, NULL, 500, '18', 5.0, NULL, NULL)"
    )


def test_reports_list_shows_rsu_vesting_forecast_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.rowCount() == len(REPORTS)
    assert pane.list_model.data(pane.list_model.index(8, 0)) == "9. RSU Vesting Forecast"


def test_selecting_rsu_vesting_forecast_report_shows_table_hides_others(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_net_worth_report(pane)
    assert pane.chart_view.isVisible()

    _select_rsu_vesting_forecast_report(pane)
    assert pane.rsu_vesting_forecast_table_view.isVisible()
    assert not pane.rsu_vesting_charts_panel.isVisible()
    assert not pane.chart_view.isVisible()
    assert not pane.category_table_view.isVisible()
    assert not pane.investment_table_view.isVisible()
    assert not pane.assets_investments_table_view.isVisible()
    assert not pane.recurring_table_view.isVisible()
    assert not pane.range_controls_row.isVisible()
    assert not pane.range_label.isVisible()
    assert pane.view_selector_row.isVisible()
    assert pane.rsu_vesting_controls_row.isVisible()


def test_rsu_vesting_forecast_report_view_selector_offers_table_and_chart(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_rsu_vesting_forecast_report(pane)
    items = [pane.view_selector.itemText(i) for i in range(pane.view_selector.count())]
    assert items == ["Table", "Chart"]


def test_rsu_vesting_forecast_report_lists_upcoming_vests_with_estimated_value(qapp, dict_conn):
    _add_future_vest(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_rsu_vesting_forecast_report(pane)

    view = pane.rsu_vesting_forecast_table_view
    assert _table_cell(view, 0, 0) == "2099-06-15"
    assert _table_cell(view, 0, 1) == "Brokerage A"
    assert _table_cell(view, 0, 2) == "Vanguard Total Stock Market Index"
    assert _table_cell(view, 0, 3) == "5.0000"
    assert _table_cell(view, 0, 5) == "113.15"
    assert _table_cell(view, 1, 2) == "Total 2099"
    assert _table_cell(view, 1, 5) == "113.15"
    assert _table_cell(view, 2, 2) == "Total"
    assert _table_cell(view, 2, 5) == "113.15"

    model = pane.rsu_vesting_forecast_table_model
    assert model.data(model.index(1, 2), Qt.FontRole).bold()
    assert model.data(model.index(0, 2), Qt.FontRole) is None


def test_rsu_vesting_forecast_report_defaults_tax_rate_to_35_percent(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_rsu_vesting_forecast_report(pane)
    assert pane.rsu_vesting_tax_rate_spinbox.value() == 35.0


def test_rsu_vesting_forecast_report_shows_shares_taxed_and_tax_columns(qapp, dict_conn):
    _add_future_vest(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_rsu_vesting_forecast_report(pane)

    pane.rsu_vesting_tax_rate_spinbox.setValue(20.0)

    view = pane.rsu_vesting_forecast_table_view
    assert _table_cell(view, 0, 4) == "1.0000"  # shares taxed: 5 shares * 20%
    assert _table_cell(view, 0, 5) == "113.15"  # est. value, unaffected by tax rate
    assert _table_cell(view, 0, 6) == "22.63"  # est. tax: 113.15 * 20%
    assert _table_cell(view, 0, 7) == "90.52"  # net of tax: 113.15 - 22.63


def test_changing_rsu_vesting_tax_rate_persists_setting(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_rsu_vesting_forecast_report(pane)

    pane.rsu_vesting_tax_rate_spinbox.setValue(22.5)

    assert load_rsu_tax_settings()["tax_rate"] == 22.5


def test_reselecting_rsu_vesting_forecast_report_loads_persisted_tax_rate(qapp, dict_conn):
    save_rsu_tax_settings({"tax_rate": 28.0})
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_rsu_vesting_forecast_report(pane)
    assert pane.rsu_vesting_tax_rate_spinbox.value() == 28.0


def test_switching_rsu_vesting_forecast_to_chart_shows_charts_and_hides_table(qapp, dict_conn):
    _add_future_vest(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_rsu_vesting_forecast_report(pane)

    pane.view_selector.setCurrentText("Chart")

    assert pane.rsu_vesting_charts_panel.isVisible()
    assert not pane.rsu_vesting_forecast_table_view.isVisible()
    shares_chart = pane.rsu_vesting_shares_chart_view.chart()
    value_chart = pane.rsu_vesting_value_chart_view.chart()
    assert len(shares_chart.series()) == 2
    assert len(value_chart.series()) == 2
    assert shares_chart.series()[0].count() == 1
    assert shares_chart.series()[1].count() == 1
    assert value_chart.series()[0].count() == 1
    assert value_chart.series()[1].count() == 1


def test_changing_rsu_vesting_tax_rate_rerenders_visible_charts(qapp, dict_conn):
    _add_future_vest(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_rsu_vesting_forecast_report(pane)
    pane.view_selector.setCurrentText("Chart")

    pane.rsu_vesting_tax_rate_spinbox.setValue(20.0)

    tax_series = pane.rsu_vesting_value_chart_view.chart().series()[1]
    assert round(tax_series.at(tax_series.count() - 1).y(), 2) == 22.63  # 113.15 * 20%


def test_selecting_other_report_after_rsu_vesting_forecast_hides_its_table(qapp, dict_conn):
    _add_future_vest(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_rsu_vesting_forecast_report(pane)
    _select_net_worth_report(pane)

    assert not pane.rsu_vesting_forecast_table_view.isVisible()
    assert not pane.rsu_vesting_charts_panel.isVisible()
    assert not pane.rsu_vesting_controls_row.isVisible()
    assert pane.range_controls_row.isVisible()
    assert pane.range_label.isVisible()
