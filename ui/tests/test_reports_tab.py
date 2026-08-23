from datetime import date

from PySide6.QtCore import QDate, QItemSelectionModel, Qt
from PySide6.QtWidgets import QDialog

import reports_tab
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
