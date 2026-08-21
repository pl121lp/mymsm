from datetime import date

from PySide6.QtCore import QDate, QItemSelectionModel, Qt

from reports_tab import REPORTS, ReportsPane


def _select_net_worth_report(pane):
    pane.list_view.selectionModel().select(
        pane.list_model.index(0, 0), QItemSelectionModel.Select
    )


def test_reports_list_view_supports_copy(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_view.contextMenuPolicy() == Qt.CustomContextMenu


def test_reports_list_shows_net_worth_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.rowCount() == len(REPORTS)
    assert pane.list_model.data(pane.list_model.index(0, 0)) == "Net worth over time"


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
