from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QPushButton

from main_window import MainWindow


def test_summary_labels_are_mouse_selectable_for_copying(qapp, conn):
    window = MainWindow(conn)
    labels = [
        window.total_label,
        window.account_details_label,
        window.details_name_value,
        window.details_type_value,
        window.details_currency_value,
        window.details_opening_balance_value,
        window.details_balance_value,
        window.details_status_value,
    ]
    for label in labels:
        assert label.textInteractionFlags() & Qt.TextSelectableByMouse


def test_account_rows_have_add_record_button(qapp, conn):
    window = MainWindow(conn)
    actions_col = window.account_model.COLUMNS.index("Actions")
    container = window.account_view.indexWidget(window.account_model.index(0, actions_col))
    button_texts = [child.text() for child in container.findChildren(QPushButton)]
    assert "Add Record" in button_texts


def test_add_record_button_reloads_account_on_accept(qapp, conn, monkeypatch):
    import add_record_dialog

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)
    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", lambda self: QDialog.Accepted)

    window = MainWindow(conn)
    reload_calls.clear()  # drop the reload that happened during __init__

    window._on_add_record_button_clicked(1)  # row 1 = Checking (cash account, see conn fixture ordering)

    assert reload_calls == [True]
    assert window.statusBar().currentMessage() == "Record added."


def test_add_record_button_does_nothing_on_cancel(qapp, conn, monkeypatch):
    import add_record_dialog

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)
    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", lambda self: QDialog.Rejected)

    window = MainWindow(conn)
    reload_calls.clear()

    window._on_add_record_button_clicked(1)

    assert reload_calls == []
