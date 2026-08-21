from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QMessageBox, QPushButton

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
    button_tooltips = [child.toolTip() for child in container.findChildren(QPushButton)]
    assert "Add Record" in button_tooltips


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


def test_add_record_button_reloads_dictionaries_pane(qapp, conn, monkeypatch):
    import add_record_dialog
    import writes
    from datetime import date
    from decimal import Decimal

    def fake_exec(self):
        writes.add_transaction(
            self._conn, self._account_id, date(2024, 4, 1), Decimal("-5.00"),
            payee_name="Brand New Payee",
        )
        return QDialog.Accepted

    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", fake_exec)

    window = MainWindow(conn)
    window._on_add_record_button_clicked(1)  # row 1 = Checking (cash account, see conn fixture ordering)

    payee_names = [
        window.payees_pane.list_model.data(window.payees_pane.list_model.index(r))
        for r in range(window.payees_pane.list_model.rowCount())
    ]
    assert "Brand New Payee" in payee_names


def test_new_account_button_exists(qapp, conn):
    window = MainWindow(conn)
    assert isinstance(window.new_account_button, QPushButton)
    assert window.new_account_button.text() == "New Account"


def test_new_account_button_reloads_accounts_on_accept(qapp, conn, monkeypatch):
    import add_account_dialog

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)
    monkeypatch.setattr(add_account_dialog.AddAccountDialog, "exec", lambda self: QDialog.Accepted)

    window = MainWindow(conn)
    reload_calls.clear()  # drop the reload that happened during __init__

    window._on_new_account_button_clicked()

    assert reload_calls == [True]
    assert window.statusBar().currentMessage() == "Account added."


def test_new_account_button_does_nothing_on_cancel(qapp, conn, monkeypatch):
    import add_account_dialog

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)
    monkeypatch.setattr(add_account_dialog.AddAccountDialog, "exec", lambda self: QDialog.Rejected)

    window = MainWindow(conn)
    reload_calls.clear()

    window._on_new_account_button_clicked()

    assert reload_calls == []


def test_open_account_row_has_close_button(qapp, conn):
    window = MainWindow(conn)
    actions_col = window.account_model.COLUMNS.index("Actions")
    # row 1 = Checking, an open account (see conn fixture ordering).
    container = window.account_view.indexWidget(window.account_model.index(1, actions_col))
    button_tooltips = [child.toolTip() for child in container.findChildren(QPushButton)]
    assert "Close" in button_tooltips
    assert "Reopen" not in button_tooltips


def test_closed_account_row_has_reopen_button(qapp, conn):
    window = MainWindow(conn)
    window.show_closed_checkbox.setChecked(True)
    actions_col = window.account_model.COLUMNS.index("Actions")
    closed_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[1] == "Old Card"
    )
    container = window.account_view.indexWidget(window.account_model.index(closed_row, actions_col))
    button_tooltips = [child.toolTip() for child in container.findChildren(QPushButton)]
    assert "Reopen" in button_tooltips
    assert "Close" not in button_tooltips


def test_close_button_closes_account_and_reloads(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.Yes)

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)

    window = MainWindow(conn)
    reload_calls.clear()

    window._on_toggle_closed_button_clicked(1)  # row 1 = Checking (open, see conn fixture ordering)

    row = conn.execute("SELECT is_closed FROM accounts WHERE account_id = 1").fetchone()
    assert row == (True,)
    assert reload_calls == [True]
    assert window.statusBar().currentMessage() == "Account closed."


def test_close_button_does_nothing_when_not_confirmed(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.No)

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)

    window = MainWindow(conn)
    reload_calls.clear()

    window._on_toggle_closed_button_clicked(1)  # row 1 = Checking (open, see conn fixture ordering)

    row = conn.execute("SELECT is_closed FROM accounts WHERE account_id = 1").fetchone()
    assert row == (False,)
    assert reload_calls == []


def test_reopen_button_reopens_account_and_reloads(qapp, conn, monkeypatch):
    window = MainWindow(conn)
    window.show_closed_checkbox.setChecked(True)
    closed_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[1] == "Old Card"
    )

    window._on_toggle_closed_button_clicked(closed_row)

    row = conn.execute("SELECT is_closed FROM accounts WHERE account_id = 2").fetchone()
    assert row == (False,)
    assert window.statusBar().currentMessage() == "Account reopened."


def test_context_actions_empty_for_open_account_row(qapp, conn):
    window = MainWindow(conn)
    # row 1 = Checking, an open account (see conn fixture ordering).
    assert window._account_context_actions(1) == []


def test_context_actions_include_delete_for_closed_account_row(qapp, conn):
    window = MainWindow(conn)
    window.show_closed_checkbox.setChecked(True)
    closed_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[1] == "Old Card"
    )
    labels = [label for label, _callback in window._account_context_actions(closed_row)]
    assert labels == ["Delete Account"]


def test_delete_account_does_nothing_when_not_confirmed(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.No)

    window = MainWindow(conn)
    window.show_closed_checkbox.setChecked(True)
    closed_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[1] == "Old Card"
    )

    window._on_delete_account_clicked(closed_row)

    row = conn.execute("SELECT account_id FROM accounts WHERE account_id = 2").fetchone()
    assert row is not None


def test_delete_account_removes_account_and_reloads_on_confirm(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.Yes)

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)

    window = MainWindow(conn)
    window.show_closed_checkbox.setChecked(True)
    closed_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[1] == "Old Card"
    )
    reload_calls.clear()

    window._on_delete_account_clicked(closed_row)

    row = conn.execute("SELECT account_id FROM accounts WHERE account_id = 2").fetchone()
    assert row is None
    assert reload_calls == [True]
    assert window.statusBar().currentMessage() == "Account 'Old Card' deleted."


def test_delete_account_confirmation_mentions_transaction_count(qapp, conn, monkeypatch):
    # account_id 1 ("Checking") has 2 seeded transactions; close it so the
    # delete action is available, then confirm the count is in the prompt.
    conn.execute("UPDATE accounts SET is_closed = TRUE WHERE account_id = 1")
    seen_messages = []

    def fake_question(*args, **kwargs):
        seen_messages.append(args[2])
        return QMessageBox.No

    monkeypatch.setattr(QMessageBox, "question", fake_question)

    window = MainWindow(conn)
    window.show_closed_checkbox.setChecked(True)
    closed_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[1] == "Checking"
    )

    window._on_delete_account_clicked(closed_row)

    assert "2" in seen_messages[0]


def test_transaction_double_click_opens_edit_dialog_for_clicked_transaction(qapp, conn, monkeypatch):
    import add_record_dialog

    seen_transactions = []
    original_init = add_record_dialog.AddRecordDialog.__init__

    def spy_init(self, conn, account_id, account_type, transaction=None, parent=None):
        seen_transactions.append(transaction)
        original_init(self, conn, account_id, account_type, transaction=transaction, parent=parent)

    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "__init__", spy_init)
    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", lambda self: QDialog.Rejected)

    window = MainWindow(conn)
    window.account_view.selectRow(1)  # row 1 = Checking (cash account, see conn fixture ordering)

    window._on_transaction_double_clicked(window.transaction_model.index(0, 0))

    assert len(seen_transactions) == 1
    assert seen_transactions[0] == window.transaction_model.transaction_at(0)


def test_transaction_edit_reloads_and_shows_status_on_accept(qapp, conn, monkeypatch):
    import add_record_dialog

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)
    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", lambda self: QDialog.Accepted)

    window = MainWindow(conn)
    window.account_view.selectRow(1)
    reload_calls.clear()  # drop the reload from selecting the row

    window._on_transaction_double_clicked(window.transaction_model.index(0, 0))

    assert reload_calls == [True]
    assert window.statusBar().currentMessage() == "Record updated."


def test_search_tab_is_present_and_holds_the_search_pane(qapp, conn):
    from search_tab import SearchPane

    window = MainWindow(conn)
    tabs = window.centralWidget()
    search_index = next(i for i in range(tabs.count()) if tabs.tabText(i) == "Search")
    assert tabs.widget(search_index) is window.search_pane
    assert isinstance(window.search_pane, SearchPane)


def test_search_pane_edit_reloads_accounts_and_dictionaries_panes(qapp, conn, monkeypatch):
    import add_record_dialog
    import writes
    from datetime import date
    from decimal import Decimal

    def fake_exec(self):
        writes.add_transaction(
            self._conn, self._account_id, date(2024, 4, 1), Decimal("-5.00"),
            payee_name="Brand New Payee",
        )
        return QDialog.Accepted

    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", fake_exec)

    window = MainWindow(conn)
    window.search_pane.payee_edit.setText("Store A")
    window.search_pane.search_button.click()

    window.search_pane._on_result_double_clicked(window.search_pane.result_model.index(0, 0))

    payee_names = [
        window.payees_pane.list_model.data(window.payees_pane.list_model.index(r))
        for r in range(window.payees_pane.list_model.rowCount())
    ]
    assert "Brand New Payee" in payee_names


def test_transaction_edit_does_nothing_on_cancel(qapp, conn, monkeypatch):
    import add_record_dialog

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)
    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", lambda self: QDialog.Rejected)

    window = MainWindow(conn)
    window.account_view.selectRow(1)
    reload_calls.clear()

    window._on_transaction_double_clicked(window.transaction_model.index(0, 0))

    assert reload_calls == []
    assert window.statusBar().currentMessage() != "Record updated."
