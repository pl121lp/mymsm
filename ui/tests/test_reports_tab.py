from PySide6.QtCore import QItemSelectionModel, Qt

from reports_tab import REPORTS, ReportsPane


def test_reports_list_view_supports_copy(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_view.contextMenuPolicy() == Qt.CustomContextMenu


def test_reports_list_shows_net_worth_report(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    assert pane.list_model.rowCount() == len(REPORTS)
    assert pane.list_model.data(pane.list_model.index(0, 0)) == "Net worth over time"


def test_selecting_net_worth_report_draws_a_bar_chart(qapp, dict_conn):
    pane = ReportsPane(dict_conn, report_error=lambda msg: None, to_usd=lambda cur, amt: amt)
    pane.list_view.selectionModel().select(
        pane.list_model.index(0, 0), QItemSelectionModel.Select
    )
    chart = pane.chart_view.chart()
    assert chart is not None
    assert len(chart.series()) == 1
