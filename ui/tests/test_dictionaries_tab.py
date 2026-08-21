from PySide6.QtCore import Qt

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
