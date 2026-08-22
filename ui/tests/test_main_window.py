from datetime import date
from decimal import Decimal

from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QDialog, QMessageBox, QPushButton

from main_window import MainWindow


def test_summary_labels_are_mouse_selectable_for_copying(qapp, conn):
    window = MainWindow(conn)
    labels = [window.total_label, window.account_details_label]
    for label in labels:
        assert label.textInteractionFlags() & Qt.TextSelectableByMouse


def test_accounts_table_has_no_actions_column(qapp, conn):
    window = MainWindow(conn)
    assert "Actions" not in window.account_model.COLUMNS


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
    window.account_view.selectRow(1)  # row 1 = Checking (cash account, see conn fixture ordering)
    reload_calls.clear()  # drop the reload that happened during __init__

    window._on_add_record_button_clicked()

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
    window.account_view.selectRow(1)
    reload_calls.clear()

    window._on_add_record_button_clicked()

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
    window.account_view.selectRow(1)  # row 1 = Checking (cash account, see conn fixture ordering)
    window._on_add_record_button_clicked()

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


def test_import_button_exists(qapp, conn):
    window = MainWindow(conn)
    assert isinstance(window.import_button, QPushButton)
    assert window.import_button.text() == "Import"


def test_import_button_does_nothing_when_no_file_selected(qapp, conn, monkeypatch):
    import main_window

    parse_calls = []
    monkeypatch.setattr(
        main_window.QFileDialog, "getOpenFileName", lambda *a, **k: ("", "")
    )
    monkeypatch.setattr(main_window, "parse_qfx", lambda path: parse_calls.append(path))

    window = MainWindow(conn)
    window._on_import_button_clicked()

    assert parse_calls == []


def test_import_button_shows_status_when_qfx_file_has_no_records(qapp, conn, monkeypatch):
    import main_window

    monkeypatch.setattr(
        main_window.QFileDialog, "getOpenFileName", lambda *a, **k: ("sample.qfx", "")
    )
    monkeypatch.setattr(main_window, "parse_qfx", lambda path: [])

    window = MainWindow(conn)
    window._on_import_button_clicked()

    assert window.statusBar().currentMessage() == "No transactions found in QFX file."


def test_import_button_opens_dialog_and_refreshes_accounts_on_accept(qapp, conn, monkeypatch):
    import import_qfx_dialog
    import main_window
    from qfx_import import QfxRecord

    fake_record = QfxRecord(
        trn_type="DEBIT", txn_date=date(2024, 4, 1), amount=Decimal("-9.00"),
        fitid="1", name="Brand New Payee", memo="", checknum="",
    )
    monkeypatch.setattr(
        main_window.QFileDialog, "getOpenFileName", lambda *a, **k: ("sample.qfx", "")
    )
    monkeypatch.setattr(main_window, "parse_qfx", lambda path: [fake_record])

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)

    def fake_exec(self):
        self.imported_count = 1
        return QDialog.Accepted

    monkeypatch.setattr(import_qfx_dialog.ImportQfxDialog, "exec", fake_exec)

    window = MainWindow(conn)
    reload_calls.clear()  # drop the reload that happened during __init__

    window._on_import_button_clicked()

    assert reload_calls == [True]
    assert window.statusBar().currentMessage() == "Imported 1 transaction(s)."


def test_import_button_does_nothing_on_discard(qapp, conn, monkeypatch):
    import import_qfx_dialog
    import main_window
    from qfx_import import QfxRecord

    fake_record = QfxRecord(
        trn_type="DEBIT", txn_date=date(2024, 4, 1), amount=Decimal("-9.00"),
        fitid="1", name="Brand New Payee", memo="", checknum="",
    )
    monkeypatch.setattr(
        main_window.QFileDialog, "getOpenFileName", lambda *a, **k: ("sample.qfx", "")
    )
    monkeypatch.setattr(main_window, "parse_qfx", lambda path: [fake_record])

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)
    monkeypatch.setattr(import_qfx_dialog.ImportQfxDialog, "exec", lambda self: QDialog.Rejected)

    window = MainWindow(conn)
    reload_calls.clear()

    window._on_import_button_clicked()

    assert reload_calls == []


def test_import_button_defaults_to_selected_account(qapp, conn, monkeypatch):
    import import_qfx_dialog
    import main_window
    from qfx_import import QfxRecord

    fake_record = QfxRecord(
        trn_type="DEBIT", txn_date=date(2024, 4, 1), amount=Decimal("-9.00"),
        fitid="1", name="Brand New Payee", memo="", checknum="",
    )
    monkeypatch.setattr(
        main_window.QFileDialog, "getOpenFileName", lambda *a, **k: ("sample.qfx", "")
    )
    monkeypatch.setattr(main_window, "parse_qfx", lambda path: [fake_record])

    captured = {}
    original_init = import_qfx_dialog.ImportQfxDialog.__init__

    def spy_init(self, conn, records, default_account_id=None, parent=None):
        captured["default_account_id"] = default_account_id
        original_init(self, conn, records, default_account_id=default_account_id, parent=parent)

    monkeypatch.setattr(import_qfx_dialog.ImportQfxDialog, "__init__", spy_init)
    monkeypatch.setattr(import_qfx_dialog.ImportQfxDialog, "exec", lambda self: QDialog.Rejected)

    window = MainWindow(conn)
    checking_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[0] == 1
    )
    window.account_view.selectRow(checking_row)

    window._on_import_button_clicked()

    assert captured["default_account_id"] == 1


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


def test_context_actions_offer_close_for_open_account_row(qapp, conn):
    window = MainWindow(conn)
    # row 1 = Checking, an open account (see conn fixture ordering).
    labels = [label for label, _callback in window._account_context_actions(1)]
    assert labels == ["Close Account"]


def test_context_actions_offer_reopen_and_delete_for_closed_account_row(qapp, conn):
    window = MainWindow(conn)
    window.show_closed_checkbox.setChecked(True)
    closed_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[1] == "Old Card"
    )
    labels = [label for label, _callback in window._account_context_actions(closed_row)]
    assert labels == ["Reopen Account", "Delete Account"]


def test_close_account_context_action_invokes_toggle_closed(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.Yes)
    window = MainWindow(conn)

    _label, callback = window._account_context_actions(1)[0]
    callback()

    row = conn.execute("SELECT is_closed FROM accounts WHERE account_id = 1").fetchone()
    assert row == (True,)


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


def test_header_controls_disabled_when_no_account_selected(qapp, conn):
    window = MainWindow(conn)
    assert not window.add_record_button.isEnabled()
    assert not window.account_details_button.isEnabled()
    assert not window.value_checkbox.isEnabled()


def test_header_controls_enabled_when_account_selected(qapp, conn):
    window = MainWindow(conn)
    window.account_view.selectRow(1)  # row 1 = Checking (see conn fixture ordering)
    assert window.add_record_button.isEnabled()
    assert window.account_details_button.isEnabled()
    assert window.value_checkbox.isEnabled()


def test_account_details_button_opens_dialog_with_selected_account_fields(qapp, conn, monkeypatch):
    import account_details_dialog

    captured = {}
    original_init = account_details_dialog.AccountDetailsDialog.__init__

    def spy_init(self, **kwargs):
        captured.update(kwargs)
        original_init(self, **kwargs)

    monkeypatch.setattr(account_details_dialog.AccountDetailsDialog, "__init__", spy_init)
    monkeypatch.setattr(account_details_dialog.AccountDetailsDialog, "exec", lambda self: QDialog.Accepted)

    window = MainWindow(conn)
    window.account_view.selectRow(1)  # row 1 = Checking (open, USD, see conn fixture ordering)

    window._on_account_details_button_clicked()

    assert captured["account_id"] == 1
    assert captured["name"] == "Checking"
    assert captured["currency"] == "USD"
    assert captured["opening_balance"] == Decimal("100.00")
    assert captured["status_text"] == "Open"
    assert "1,047.70" in captured["balance_text"]  # opening 100.00 plus seeded transactions


def test_account_details_button_shows_closed_status_for_closed_account(qapp, conn, monkeypatch):
    import account_details_dialog

    captured = {}
    original_init = account_details_dialog.AccountDetailsDialog.__init__

    def spy_init(self, **kwargs):
        captured.update(kwargs)
        original_init(self, **kwargs)

    monkeypatch.setattr(account_details_dialog.AccountDetailsDialog, "__init__", spy_init)
    monkeypatch.setattr(account_details_dialog.AccountDetailsDialog, "exec", lambda self: QDialog.Accepted)

    window = MainWindow(conn)
    window.show_closed_checkbox.setChecked(True)
    closed_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[1] == "Old Card"
    )
    window.account_view.selectRow(closed_row)

    window._on_account_details_button_clicked()

    assert captured["name"] == "Old Card"  # no "(CLOSED)" prefix; status_text conveys that
    assert captured["status_text"] == "Closed"


def test_account_details_save_renames_account_and_refreshes_list(qapp, conn, monkeypatch):
    import account_details_dialog
    import writes

    def fake_exec(self):
        writes.update_account(
            self._conn, self._account_id, name="Checking Renamed", opening_balance=Decimal("250.00")
        )
        return QDialog.Accepted

    monkeypatch.setattr(account_details_dialog.AccountDetailsDialog, "exec", fake_exec)

    window = MainWindow(conn)
    window.account_view.selectRow(1)  # row 1 = Checking (see conn fixture ordering)

    window._on_account_details_button_clicked()

    selected_row = window.account_view.selectionModel().selectedRows()[0].row()
    account_id, name, *_ = window.account_model.account_at(selected_row)
    assert account_id == 1
    assert name == "Checking Renamed"
    assert window.statusBar().currentMessage() == "Account updated."


def test_value_checkbox_checked_shows_chart_page(qapp, conn):
    window = MainWindow(conn)
    window.account_view.selectRow(1)  # row 1 = Checking (see conn fixture ordering)

    window.value_checkbox.setChecked(True)

    assert window.content_stack.currentWidget() is window.value_chart_view


def test_value_checkbox_unchecked_shows_transaction_table(qapp, conn):
    window = MainWindow(conn)
    window.account_view.selectRow(1)
    window.value_checkbox.setChecked(True)

    window.value_checkbox.setChecked(False)

    assert window.content_stack.currentWidget() is window.transaction_view


def test_selecting_new_account_resets_value_checkbox_and_content_page(qapp, conn):
    window = MainWindow(conn)
    window.account_view.selectRow(1)  # row 1 = Checking (see conn fixture ordering)
    window.value_checkbox.setChecked(True)

    brokerage_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[1] == "Brokerage"
    )
    window.account_view.selectRow(brokerage_row)

    assert not window.value_checkbox.isChecked()
    assert window.content_stack.currentWidget() is window.transaction_view


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


def test_transaction_context_actions_include_delete_record(qapp, conn):
    window = MainWindow(conn)
    window.account_view.selectRow(1)  # row 1 = Checking (cash account, see conn fixture ordering)

    labels = [label for label, _callback in window._transaction_context_actions(0)]

    assert labels == ["Delete Record"]


def test_delete_record_does_nothing_when_not_confirmed(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.No)

    window = MainWindow(conn)
    window.account_view.selectRow(1)
    transaction_id = window.transaction_model.transaction_at(0)[0]

    window._on_delete_record_clicked(0)

    row = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id = ?", [transaction_id]
    ).fetchone()
    assert row is not None


def test_delete_record_removes_record_and_reloads_on_confirm(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.Yes)

    window = MainWindow(conn)
    window.account_view.selectRow(1)
    transaction_id = window.transaction_model.transaction_at(0)[0]

    window._on_delete_record_clicked(0)

    row = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id = ?", [transaction_id]
    ).fetchone()
    assert row is None
    assert window.statusBar().currentMessage() == "Record deleted."


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


def test_going_back_with_empty_history_does_nothing(qapp, conn):
    window = MainWindow(conn)

    window._go_back()  # must not raise

    assert window.tabs.currentIndex() == 0


def test_going_back_reselects_previously_selected_account(qapp, conn):
    window = MainWindow(conn)
    window.account_view.selectRow(1)  # row 1 = Checking (see conn fixture ordering)
    brokerage_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[1] == "Brokerage"
    )
    window.account_view.selectRow(brokerage_row)

    window._go_back()

    selected_row = window.account_view.selectionModel().selectedRows()[0].row()
    assert window.account_model.account_at(selected_row)[1] == "Checking"


def test_going_back_returns_to_previous_tab(qapp, conn):
    window = MainWindow(conn)
    window.tabs.setCurrentIndex(2)  # Search tab

    window._go_back()

    assert window.tabs.currentIndex() == 0  # Accounts tab


def test_going_back_twice_replays_tab_switch_then_account_switch(qapp, conn):
    window = MainWindow(conn)
    window.account_view.selectRow(1)  # Checking
    window.tabs.setCurrentIndex(2)  # Search tab
    window.tabs.setCurrentIndex(0)  # back to Accounts tab (still Checking selected)
    brokerage_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[1] == "Brokerage"
    )
    window.account_view.selectRow(brokerage_row)

    window._go_back()
    assert window.tabs.currentIndex() == 0
    selected_row = window.account_view.selectionModel().selectedRows()[0].row()
    assert window.account_model.account_at(selected_row)[1] == "Checking"

    window._go_back()
    assert window.tabs.currentIndex() == 2


def test_going_back_after_reselecting_same_account_does_not_skip_a_step(qapp, conn, monkeypatch):
    # Actions like adding a record re-select the already-selected row, which
    # must not be recorded as a spurious navigation step.
    import add_record_dialog

    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", lambda self: QDialog.Rejected)

    window = MainWindow(conn)
    window.account_view.selectRow(1)  # Checking
    brokerage_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[1] == "Brokerage"
    )
    window.account_view.selectRow(brokerage_row)
    window._on_add_record_button_clicked()  # re-selects Brokerage, dialog cancelled

    window._go_back()

    selected_row = window.account_view.selectionModel().selectedRows()[0].row()
    assert window.account_model.account_at(selected_row)[1] == "Checking"


def test_going_back_does_not_itself_get_recorded_as_a_step(qapp, conn):
    window = MainWindow(conn)
    window.account_view.selectRow(1)  # Checking
    brokerage_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[1] == "Brokerage"
    )
    window.account_view.selectRow(brokerage_row)

    window._go_back()  # -> Checking
    window._go_back()  # history should now be empty, must not bounce back to Brokerage

    selected_row = window.account_view.selectionModel().selectedRows()[0].row()
    assert window.account_model.account_at(selected_row)[1] == "Checking"


def test_mouse_back_button_press_triggers_go_back(qapp, conn):
    window = MainWindow(conn)
    calls = []
    window._go_back = lambda: calls.append(True)
    event = QMouseEvent(
        QEvent.MouseButtonPress, QPointF(0, 0), QPointF(0, 0), Qt.BackButton, Qt.BackButton, Qt.NoModifier
    )

    window.eventFilter(window, event)

    assert calls == [True]


def test_other_mouse_buttons_do_not_trigger_go_back(qapp, conn):
    window = MainWindow(conn)
    calls = []
    window._go_back = lambda: calls.append(True)
    event = QMouseEvent(
        QEvent.MouseButtonPress, QPointF(0, 0), QPointF(0, 0), Qt.LeftButton, Qt.LeftButton, Qt.NoModifier
    )

    window.eventFilter(window, event)

    assert calls == []


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
