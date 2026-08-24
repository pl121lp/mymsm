import functools
from datetime import date

import pytest
from PySide6.QtCore import QDate, QItemSelectionModel, Qt
from PySide6.QtWidgets import QDialog, QScrollArea, QSizePolicy

import reports_tab
from college_tuition_settings import (
    load_college_tuition_settings as _real_load_college_tuition_settings,
    save_college_tuition_settings as _real_save_college_tuition_settings,
)
from projection_settings import (
    load_projection_settings as _real_load_projection_settings,
    save_projection_settings as _real_save_projection_settings,
)
from reports_tab import REPORTS, ReportsPane


def _select_net_worth_report(pane):
    pane.list_view.selectionModel().select(
        pane.list_model.index(0, 0), QItemSelectionModel.ClearAndSelect
    )


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
    assert pane.list_model.data(pane.list_model.index(0, 0)) == "Net worth over time"


def test_reports_list_shows_spending_by_category_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.data(pane.list_model.index(1, 0)) == "Spending by category"


def test_reports_list_shows_income_by_category_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.data(pane.list_model.index(2, 0)) == "Income by category"


def test_reports_list_shows_investment_analysis_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.data(pane.list_model.index(3, 0)) == "Investment analysis"


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


def test_updating_range_redraws_chart_for_narrower_window(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_net_worth_report(pane)

    pane.start_date_edit.setDate(QDate(2024, 2, 1))
    pane.end_date_edit.setDate(QDate(2024, 3, 1))
    pane.update_range_button.click()

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
    assert pane.list_model.data(pane.list_model.index(4, 0)) == "Net Worth Projection"


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
    monkeypatch.setattr(reports_tab, "load_projection_settings", lambda: {})
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_projection_report(pane)

    assert pane.projection_controls.starting_investment_value_spinbox.value() == pytest.approx(426.30)


def test_selecting_projection_report_loads_persisted_settings(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(
        reports_tab, "load_projection_settings", lambda: {"retirement_age": 70, "annual_income": 12345.0}
    )
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_projection_report(pane)

    assert pane.projection_controls.retirement_age_spinbox.value() == 70
    assert pane.projection_controls.annual_income_spinbox.value() == pytest.approx(12345.0)


def test_selecting_projection_report_renders_a_net_worth_line_series(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_settings", lambda: {})
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_projection_report(pane)

    chart = pane.chart_view.chart()
    series = chart.series()
    assert [s.name() for s in series if s.name()] == ["Net Worth"]
    net_worth_series = series[0]
    assert net_worth_series.count() > 1
    assert net_worth_series.at(0).y() == pytest.approx(426.30)


def test_selecting_projection_report_populates_house_account_choices(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_settings", lambda: {})
    dict_conn.execute("INSERT INTO accounts VALUES (5, 'House', '3', FALSE, 300000.00, 'USD', NULL)")
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)

    _select_projection_report(pane)

    combo = pane.projection_controls.house_account_combo
    assert [combo.itemText(i) for i in range(combo.count())] == ["None", "House"]


def test_selecting_house_account_adds_its_value_in_the_sale_year(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_settings", lambda: {})
    dict_conn.execute("INSERT INTO accounts VALUES (5, 'House', '3', FALSE, 300000.00, 'USD', NULL)")
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

    series = pane.chart_view.chart().series()[0]
    assert series.at(1).y() == pytest.approx(series.at(0).y() + 300000.00)


def test_clicking_update_in_projection_panel_saves_settings_and_rerenders(qapp, dict_conn, monkeypatch):
    monkeypatch.setattr(reports_tab, "load_projection_settings", lambda: {})
    saved = {}
    monkeypatch.setattr(reports_tab, "save_projection_settings", saved.update)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)

    pane.projection_controls.retirement_age_spinbox.setValue(70)
    pane.projection_controls.update_button.click()

    assert saved["retirement_age"] == 70
    assert "starting_investment_value" not in saved


def test_persisted_settings_round_trip_through_panel(qapp, dict_conn, monkeypatch, tmp_path):
    settings_path = tmp_path / "projection_settings.json"
    dict_conn.execute("INSERT INTO accounts VALUES (5, 'House', '3', FALSE, 300000.00, 'USD', NULL)")
    monkeypatch.setattr(
        reports_tab, "load_projection_settings",
        functools.partial(_real_load_projection_settings, path=settings_path),
    )
    monkeypatch.setattr(
        reports_tab, "save_projection_settings",
        functools.partial(_real_save_projection_settings, path=settings_path),
    )

    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_projection_report(pane)
    pane.projection_controls.retirement_age_spinbox.setValue(70)
    pane.projection_controls.house_account_combo.setCurrentIndex(1)
    pane.projection_controls.update_button.click()

    pane2 = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    monkeypatch.setattr(
        reports_tab, "load_projection_settings",
        functools.partial(_real_load_projection_settings, path=settings_path),
    )
    _select_projection_report(pane2)

    assert pane2.projection_controls.retirement_age_spinbox.value() == 70
    assert pane2.projection_controls.house_account_combo.currentData() == 5


def test_reports_list_shows_college_tuition_projection_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.rowCount() == len(REPORTS)
    assert pane.list_model.data(pane.list_model.index(5, 0)) == "College Tuition Projection"


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
        "INSERT INTO accounts VALUES "
        "(5, 'House', '3', FALSE, 500000.00, 'USD', NULL), "
        "(6, 'Car Loan', '6', FALSE, -15000.00, 'USD', NULL)"
    )


def test_reports_list_shows_assets_and_investments_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.rowCount() == len(REPORTS)
    assert pane.list_model.data(pane.list_model.index(6, 0)) == "Assets and investments"


def test_selecting_assets_and_investments_report_shows_table_hides_others(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.show()
    _select_net_worth_report(pane)
    assert pane.chart_view.isVisible()

    _select_assets_and_investments_report(pane)
    assert pane.assets_investments_table_view.isVisible()
    assert not pane.chart_view.isVisible()
    assert not pane.category_table_view.isVisible()
    assert not pane.investment_table_view.isVisible()
    assert not pane.view_selector_row.isVisible()
    assert not pane.investment_controls_row.isVisible()
    assert not pane.range_controls_row.isVisible()
    assert not pane.range_label.isVisible()


def test_assets_and_investments_report_lists_accounts_by_section_with_totals(qapp, dict_conn):
    _add_asset_and_loan_accounts(dict_conn)
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    _select_assets_and_investments_report(pane)

    view = pane.assets_investments_table_view
    rows = [
        (_table_cell(view, row, 0), _table_cell(view, row, 1))
        for row in range(view.model().rowCount())
    ]
    assert rows == [
        ("Investments", ""),
        ("Brokerage A", "226.30"),
        ("Brokerage B", "200.00"),
        ("Total Investments", "426.30"),
        ("Assets", ""),
        ("House", "500,000.00"),
        ("Total Assets", "500,000.00"),
        ("Loans / Liabilities", ""),
        ("Car Loan", "15,000.00"),
        ("Total Loans", "15,000.00"),
        ("Total Balance", "485,426.30"),
    ]


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
    labels = [_table_cell(view, row, 0) for row in range(view.model().rowCount())]
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
