from datetime import date
from decimal import Decimal

import pytest
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QDialog, QMessageBox, QPushButton

import app_settings
import theme
from main_window import SETTINGS_KEY_DARK_MODE, SETTINGS_KEY_SEK_RATE, MainWindow


def test_summary_labels_are_mouse_selectable_for_copying(qapp, conn):
    window = MainWindow(conn)
    labels = [window.total_label, window.account_details_label]
    for label in labels:
        assert label.textInteractionFlags() & Qt.TextSelectableByMouse


def test_accounts_table_has_no_actions_column(qapp, conn):
    window = MainWindow(conn)
    assert "Actions" not in window.account_model.COLUMNS


def test_dark_mode_checkbox_is_tab_corner_widget(qapp, conn):
    window = MainWindow(conn)
    assert window.tabs.cornerWidget(Qt.TopRightCorner) is window.dark_mode_checkbox


def test_dark_mode_checkbox_reflects_saved_setting(qapp, conn):
    app_settings.save_app_settings(
        {SETTINGS_KEY_DARK_MODE: True}, app_settings.DEFAULT_SETTINGS_PATH
    )

    window = MainWindow(conn)
    try:
        assert window.dark_mode_checkbox.isChecked() is True
        assert theme.is_dark() is True
    finally:
        theme.apply_theme(qapp, False)


def test_toggling_dark_mode_checkbox_persists_setting(qapp, conn):
    window = MainWindow(conn)
    try:
        window.dark_mode_checkbox.setChecked(True)
        saved = app_settings.load_app_settings(app_settings.DEFAULT_SETTINGS_PATH)
        assert saved[SETTINGS_KEY_DARK_MODE] is True
        assert theme.is_dark() is True

        window.dark_mode_checkbox.setChecked(False)
        saved = app_settings.load_app_settings(app_settings.DEFAULT_SETTINGS_PATH)
        assert saved[SETTINGS_KEY_DARK_MODE] is False
        assert theme.is_dark() is False
    finally:
        theme.apply_theme(qapp, False)


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


def test_delete_account_clears_undo_stack_for_its_own_transactions(qapp, conn, monkeypatch):
    # Queue an undo command for a transaction that belongs to the account
    # being deleted, then delete the whole account. Account deletion removes
    # all of its transactions, so the queued command would otherwise become
    # stale: DeleteCommand.undo would raise on the missing row, and
    # AddCommand/EditCommand/ImportCommand.undo would silently no-op while
    # still reporting success. Deleting the account must clear the stack.
    import add_record_dialog
    import writes
    from datetime import date
    from decimal import Decimal

    def fake_exec(self):
        self.transaction_id = writes.add_transaction(
            self._conn, self._account_id, date(2024, 4, 1), Decimal("-5.00"),
        )
        return QDialog.Accepted

    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", fake_exec)

    window = MainWindow(conn)
    window.account_view.selectRow(1)  # row 1 = Checking (see conn fixture ordering)
    window._on_add_record_button_clicked()
    assert bool(window._undo_stack) is True

    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.Yes)
    checking_row = next(
        row for row in range(window.account_model.rowCount())
        if window.account_model.account_at(row)[1] == "Checking"
    )
    window._on_delete_account_clicked(checking_row)

    window._on_undo()

    assert window.statusBar().currentMessage() == "Nothing to undo."


def test_header_controls_disabled_when_no_account_selected(qapp, conn):
    window = MainWindow(conn)
    assert not window.add_record_button.isEnabled()
    assert not window.account_details_button.isEnabled()
    assert not window.value_checkbox.isEnabled()
    assert not window.add_grant_button.isEnabled()


def test_header_controls_enabled_when_account_selected(qapp, conn):
    window = MainWindow(conn)
    window.account_view.selectRow(1)  # row 1 = Checking (see conn fixture ordering)
    assert window.add_record_button.isEnabled()
    assert window.account_details_button.isEnabled()
    assert window.value_checkbox.isEnabled()


def test_add_grant_button_hidden_for_non_investment_account(qapp, conn):
    window = MainWindow(conn)
    window.show()
    window.account_view.selectRow(1)  # row 1 = Checking, a cash account
    assert not window.add_grant_button.isEnabled()
    assert not window.add_grant_button.isVisible()


def test_add_grant_button_visible_for_investment_account(qapp, conn):
    window = MainWindow(conn)
    window.show()
    window.account_view.selectRow(0)  # row 0 = Brokerage (see conn fixture ordering)
    assert window.add_grant_button.isEnabled()
    assert window.add_grant_button.isVisible()


def test_add_grant_button_hidden_when_no_account_selected(qapp, conn):
    window = MainWindow(conn)
    window.show()
    assert not window.add_grant_button.isVisible()


def test_add_grant_button_reloads_account_on_accept(qapp, conn, monkeypatch):
    import add_grant_dialog

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)

    def fake_exec(self):
        self.transaction_ids = [9001]
        return QDialog.Accepted

    monkeypatch.setattr(add_grant_dialog.AddGrantDialog, "exec", fake_exec)

    window = MainWindow(conn)
    window.account_view.selectRow(0)  # row 0 = Brokerage (see conn fixture ordering)
    reload_calls.clear()  # drop the reload that happened during __init__

    window._on_add_grant_button_clicked()

    assert reload_calls == [True]
    assert window.statusBar().currentMessage() == "Grant added."


def test_add_grant_button_does_nothing_on_cancel(qapp, conn, monkeypatch):
    import add_grant_dialog

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)
    monkeypatch.setattr(add_grant_dialog.AddGrantDialog, "exec", lambda self: QDialog.Rejected)

    window = MainWindow(conn)
    window.account_view.selectRow(0)
    reload_calls.clear()

    window._on_add_grant_button_clicked()

    assert reload_calls == []


def test_add_grant_button_pushes_undo_command(qapp, conn, monkeypatch):
    import add_grant_dialog
    import writes

    def fake_exec(self):
        self.transaction_ids = writes.add_rsu_grant(
            self._conn, self._account_id, security_name="2025 New Grant",
            grant_date=date(2024, 1, 1), total_shares=12,
            vest_frequency_months=3, vest_count=4,
        )
        return QDialog.Accepted

    monkeypatch.setattr(add_grant_dialog.AddGrantDialog, "exec", fake_exec)

    window = MainWindow(conn)
    window.account_view.selectRow(0)  # row 0 = Brokerage

    window._on_add_grant_button_clicked()

    assert bool(window._undo_stack) is True
    command = window._undo_stack.pop()
    assert command.description == "Add grant (5 record(s))"


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


def test_loan_account_header_shows_principal_and_interest_totals(qapp, loan_conn):
    window = MainWindow(loan_conn)
    window.account_view.selectRow(2)  # row 2 = Car Loan (see loan_conn fixture ordering)

    text = window.account_details_label.text()
    assert "Balance: -183.00 USD" in text
    assert "Total Principal Paid: 817.00 USD" in text
    assert "Total Interest Paid: 83.00 USD" in text


def test_loan_account_transaction_table_shows_type_column_with_interest_rows(qapp, loan_conn):
    window = MainWindow(loan_conn)
    window.account_view.selectRow(2)  # row 2 = Car Loan (see loan_conn fixture ordering)

    assert window.transaction_model.headerData(2, Qt.Horizontal) == "Type"
    kinds = {window.transaction_model.transaction_at(r)[10] for r in range(window.transaction_model.rowCount())}
    assert kinds == {"Principal", "Interest"}
    assert window.transaction_model.rowCount() == 7  # 4 principal + 3 matched interest


def test_loan_interest_total_converts_using_paying_accounts_currency(qapp, loan_conn):
    # Foreign Loan (SEK) is paid from Foreign Checking, also SEK — the
    # interest total must be converted from the paying account's currency,
    # not assumed to already match the loan's own currency.
    window = MainWindow(loan_conn)
    window.sek_rate_spinbox.setValue(0.1)  # deterministic rate for the assertion below
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Foreign Loan"
    )
    window.account_view.selectRow(row)

    text = window.account_details_label.text()
    assert "Total Interest Paid: 5.00 USD" in text  # 50.00 SEK * 0.1


def test_loan_interest_row_double_click_does_not_open_edit_dialog(qapp, loan_conn, monkeypatch):
    import add_record_dialog

    opened = []
    monkeypatch.setattr(
        add_record_dialog.AddRecordDialog, "__init__",
        lambda self, *a, **kw: opened.append(True),
    )

    window = MainWindow(loan_conn)
    window.account_view.selectRow(2)  # row 2 = Car Loan (see loan_conn fixture ordering)
    interest_row = next(
        r for r in range(window.transaction_model.rowCount())
        if window.transaction_model.transaction_at(r)[10] == "Interest"
    )

    window._on_transaction_double_clicked(window.transaction_model.index(interest_row, 0))

    assert opened == []


def test_loan_interest_row_context_actions_offer_no_delete(qapp, loan_conn):
    window = MainWindow(loan_conn)
    window.account_view.selectRow(2)  # row 2 = Car Loan (see loan_conn fixture ordering)
    interest_row = next(
        r for r in range(window.transaction_model.rowCount())
        if window.transaction_model.transaction_at(r)[10] == "Interest"
    )

    assert window._transaction_context_actions(interest_row) == []


def test_loan_principal_row_double_click_still_opens_edit_dialog(qapp, loan_conn, monkeypatch):
    import add_record_dialog

    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", lambda self: QDialog.Rejected)

    window = MainWindow(loan_conn)
    window.account_view.selectRow(2)  # row 2 = Car Loan (see loan_conn fixture ordering)
    principal_row = next(
        r for r in range(window.transaction_model.rowCount())
        if window.transaction_model.transaction_at(r)[10] == "Principal"
    )

    window._on_transaction_double_clicked(window.transaction_model.index(principal_row, 0))
    # No exception means the dialog opened normally with a real transaction.


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


def test_refresh_rate_button_requests_frankfurter_rate(qapp, conn):
    from exchange_rate import FRANKFURTER_URL

    window = MainWindow(conn)
    captured = []

    class FakeSignal:
        def connect(self, _callback):
            pass

    class FakeReply:
        finished = FakeSignal()

        def error(self):
            return None

    def fake_get(request):
        captured.append(request)
        return FakeReply()

    window._network_manager.get = fake_get

    window._on_refresh_rate_button_clicked()

    assert len(captured) == 1
    assert captured[0].url().toString() == FRANKFURTER_URL
    assert window.refresh_rate_button.isEnabled() is False


def test_apply_rate_response_updates_spinbox_on_success(qapp, conn):
    window = MainWindow(conn)
    window.refresh_rate_button.setEnabled(False)
    body = b'{"amount":1.0,"base":"SEK","date":"2024-01-01","rates":{"USD":0.1234}}'

    window._apply_rate_response(True, body)

    assert window.sek_rate_spinbox.value() == pytest.approx(0.1234)
    assert window._app_settings[SETTINGS_KEY_SEK_RATE] == pytest.approx(0.1234)
    assert "0.1234" in window.statusBar().currentMessage()
    assert window.refresh_rate_button.isEnabled() is True


def test_apply_rate_response_keeps_cached_value_on_network_failure(qapp, conn):
    window = MainWindow(conn)
    window.sek_rate_spinbox.setValue(0.2)
    window.refresh_rate_button.setEnabled(False)

    window._apply_rate_response(False, b"")

    assert window.sek_rate_spinbox.value() == pytest.approx(0.2)
    assert "saved value" in window.statusBar().currentMessage()
    assert window.refresh_rate_button.isEnabled() is True


def test_apply_rate_response_keeps_cached_value_on_bad_body(qapp, conn):
    window = MainWindow(conn)
    window.sek_rate_spinbox.setValue(0.2)

    window._apply_rate_response(True, b"not json")

    assert window.sek_rate_spinbox.value() == pytest.approx(0.2)
    assert "saved value" in window.statusBar().currentMessage()


def test_undo_with_nothing_to_undo_shows_status_message(qapp, conn):
    window = MainWindow(conn)
    window._on_undo()
    assert window.statusBar().currentMessage() == "Nothing to undo."


def test_ctrl_z_undoes_an_add(qapp, conn, monkeypatch):
    import add_record_dialog
    import writes
    from datetime import date
    from decimal import Decimal

    def fake_exec(self):
        self.transaction_id = writes.add_transaction(
            self._conn, self._account_id, date(2024, 4, 1), Decimal("-5.00"),
        )
        return QDialog.Accepted

    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", fake_exec)

    window = MainWindow(conn)
    window.account_view.selectRow(1)  # row 1 = Checking (cash account, see conn fixture ordering)
    window._on_add_record_button_clicked()
    new_id = window.transaction_model.transaction_at(0)[0]

    window._on_undo()

    row = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id = ?", [new_id]
    ).fetchone()
    assert row is None
    assert window.statusBar().currentMessage() == "Undone: Add record"


def test_ctrl_z_undoes_an_edit(qapp, conn, monkeypatch):
    import add_record_dialog

    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", lambda self: QDialog.Accepted)

    window = MainWindow(conn)
    window.account_view.selectRow(1)
    original_memo = conn.execute(
        "SELECT memo FROM transactions WHERE transaction_id = 1000"
    ).fetchone()[0]

    window._on_transaction_double_clicked(window.transaction_model.index(0, 0))
    conn.execute("UPDATE transactions SET memo = 'clobbered' WHERE transaction_id = 1000")

    window._on_undo()

    memo = conn.execute("SELECT memo FROM transactions WHERE transaction_id = 1000").fetchone()[0]
    assert memo == original_memo
    assert window.statusBar().currentMessage() == "Undone: Edit record"


def test_ctrl_z_undoes_a_delete(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.Yes)

    window = MainWindow(conn)
    window.account_view.selectRow(1)
    transaction_id = window.transaction_model.transaction_at(0)[0]

    window._on_delete_record_clicked(0)
    window._on_undo()

    row = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id = ?", [transaction_id]
    ).fetchone()
    assert row is not None
    assert window.statusBar().currentMessage() == "Undone: Delete record"


def test_ctrl_z_undoes_an_import(qapp, conn, monkeypatch):
    import import_qfx_dialog
    import main_window
    from qfx_import import QfxRecord

    def fake_exec(self):
        self.imported_transaction_ids = [9001, 9002]
        self.imported_count = 2
        conn.execute(
            "INSERT INTO transactions VALUES "
            "(9001, 1, NULL, NULL, '2024-05-01', -1.00, NULL, NULL, NULL, NULL, NULL, NULL), "
            "(9002, 1, NULL, NULL, '2024-05-02', -2.00, NULL, NULL, NULL, NULL, NULL, NULL)"
        )
        return QDialog.Accepted

    monkeypatch.setattr(import_qfx_dialog.ImportQfxDialog, "exec", fake_exec)
    # ImportQfxDialog.__init__ builds its preview tables from these records
    # before exec() is ever called, so a bare object() would blow up on
    # attribute access; contents are otherwise unused by fake_exec.
    fake_record = QfxRecord(
        trn_type="DEBIT",
        txn_date=date(2024, 5, 1),
        amount=Decimal("-1.00"),
        fitid="FAKE1",
        name="Fake Payee",
        memo="",
        checknum="",
    )
    monkeypatch.setattr(main_window, "parse_qfx", lambda path: [fake_record])
    monkeypatch.setattr(
        main_window.QFileDialog, "getOpenFileName", lambda *a, **kw: ("dummy.qfx", "")
    )

    window = MainWindow(conn)
    window.account_view.selectRow(1)

    window._on_import_button_clicked()
    window._on_undo()

    rows = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id IN (9001, 9002)"
    ).fetchall()
    assert rows == []
    assert window.statusBar().currentMessage() == "Undone: Import 2 record(s)"


def test_ctrl_z_shows_failure_message_and_drops_failed_command(qapp, conn):
    class _FailingCommand:
        description = "Fail"

        def undo(self, conn):
            raise RuntimeError("boom")

    window = MainWindow(conn)
    window._undo_stack.push(_FailingCommand())

    window._on_undo()

    assert window.statusBar().currentMessage().startswith("Failed to undo:")
    assert not window._undo_stack


def test_ctrl_z_shortcut_is_wired_to_on_undo(qapp, conn):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    window = MainWindow(conn)
    window.show()
    QTest.qWaitForWindowExposed(window)

    QTest.keyClick(window, Qt.Key_Z, Qt.ControlModifier)

    assert window.statusBar().currentMessage() == "Nothing to undo."
    window.close()


def test_amortization_checkbox_disabled_for_non_loan_account(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Checking"
    )
    window.account_view.selectRow(row)
    assert not window.amortization_checkbox.isEnabled()


def test_amortization_checkbox_enabled_for_loan_with_terms(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(row)
    assert window.amortization_checkbox.isEnabled()


def test_amortization_checkbox_disabled_with_tooltip_for_loan_missing_terms(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Legacy Loan"
    )
    window.account_view.selectRow(row)
    assert not window.amortization_checkbox.isEnabled()
    assert "No interest rate/payment data" in window.amortization_checkbox.toolTip()


def test_amortization_checkbox_hidden_for_non_loan_account(qapp, loan_conn):
    window = MainWindow(loan_conn)
    window.show()
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Checking"
    )
    window.account_view.selectRow(row)
    assert not window.amortization_checkbox.isVisible()
    window.close()


def test_amortization_checkbox_visible_for_loan_account(qapp, loan_conn):
    window = MainWindow(loan_conn)
    window.show()
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(row)
    assert window.amortization_checkbox.isVisible()
    window.close()


def test_amortization_checkbox_visible_but_disabled_for_loan_missing_terms(qapp, loan_conn):
    window = MainWindow(loan_conn)
    window.show()
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Legacy Loan"
    )
    window.account_view.selectRow(row)
    assert window.amortization_checkbox.isVisible()
    assert not window.amortization_checkbox.isEnabled()
    window.close()


def test_amortization_checkbox_hidden_when_no_account_selected(qapp, loan_conn):
    window = MainWindow(loan_conn)
    window.show()
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(row)
    window.account_view.clearSelection()
    assert not window.amortization_checkbox.isVisible()
    window.close()


def test_amortization_checkbox_checked_shows_amortization_page(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(row)

    window.amortization_checkbox.setChecked(True)

    assert window.content_stack.currentWidget() is window.amortization_chart_view


def test_amortization_checkbox_unchecked_shows_transaction_table(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(row)
    window.amortization_checkbox.setChecked(True)

    window.amortization_checkbox.setChecked(False)

    assert window.content_stack.currentWidget() is window.transaction_view


def test_checking_amortization_unchecks_value_checkbox(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(row)
    window.value_checkbox.setChecked(True)

    window.amortization_checkbox.setChecked(True)

    assert not window.value_checkbox.isChecked()
    assert window.content_stack.currentWidget() is window.amortization_chart_view


def test_checking_value_unchecks_amortization_checkbox(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(row)
    window.amortization_checkbox.setChecked(True)

    window.value_checkbox.setChecked(True)

    assert not window.amortization_checkbox.isChecked()
    assert window.content_stack.currentWidget() is window.value_chart_view


def test_selecting_new_account_resets_amortization_checkbox(qapp, loan_conn):
    window = MainWindow(loan_conn)
    car_loan_row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(car_loan_row)
    window.amortization_checkbox.setChecked(True)

    checking_row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Checking"
    )
    window.account_view.selectRow(checking_row)

    assert not window.amortization_checkbox.isChecked()
    assert window.content_stack.currentWidget() is window.transaction_view


def test_amortization_chart_shows_actual_and_projected_series_for_amortizing_loan(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(row)

    window.amortization_checkbox.setChecked(True)

    series_names = {s.name() for s in window.amortization_chart_view.chart().series() if s.name()}
    assert series_names == {"Actual", "Projected"}


def test_amortization_view_shows_status_message_when_loan_does_not_amortize(qapp, loan_conn):
    loan_conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id, loan_interest_rate, loan_payment_amount, "
        "loan_payment_count) VALUES "
        "(6, 'Bad Loan', '6', FALSE, -100000.00, 'USD', NULL, 0.24, 10.00, 360)"
    )
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Bad Loan"
    )
    window.account_view.selectRow(row)

    window.amortization_checkbox.setChecked(True)

    assert window.content_stack.currentWidget() is window.amortization_chart_view
    assert "doesn't cover its interest" in window.statusBar().currentMessage()
    series_names = {s.name() for s in window.amortization_chart_view.chart().series() if s.name()}
    assert series_names == {"Actual"}
