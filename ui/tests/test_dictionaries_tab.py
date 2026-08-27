from PySide6.QtCore import Qt

import theme
from dictionaries_tab import CategoriesPane, InvestmentsPane, PayeesPane


def test_categories_list_view_supports_copy(qapp, dict_conn):
    pane = CategoriesPane(dict_conn, report_error=lambda msg: None)
    assert pane.list_view.contextMenuPolicy() == Qt.CustomContextMenu


def test_payees_list_view_supports_copy(qapp, dict_conn):
    pane = PayeesPane(dict_conn, report_error=lambda msg: None)
    assert pane.list_view.contextMenuPolicy() == Qt.CustomContextMenu


def test_investments_list_view_supports_copy(qapp, dict_conn):
    pane = InvestmentsPane(dict_conn, report_error=lambda msg: None)
    assert pane.list_view.contextMenuPolicy() == Qt.CustomContextMenu


def test_investments_empty_charts_use_dark_theme_when_dark_mode_is_active(qapp, dict_conn):
    theme.apply_theme(qapp, True)
    try:
        pane = InvestmentsPane(dict_conn, report_error=lambda msg: None)
        assert pane.price_chart_view.chart().theme() == theme.chart_theme()
        assert pane.quantity_chart_view.chart().theme() == theme.chart_theme()

        pane.list_view.selectionModel().clearSelection()
        assert pane.price_chart_view.chart().theme() == theme.chart_theme()
        assert pane.quantity_chart_view.chart().theme() == theme.chart_theme()
    finally:
        theme.apply_theme(qapp, False)
