from datetime import date
from decimal import Decimal

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDialog, QDialogButtonBox

from add_record_dialog import AddRecordDialog

CASH_TRANSACTION = (
    1000, date(2024, 3, 15), "Store A", "Groceries", "weekly shop", Decimal("-52.30"),
    None, None, None, None,
)

INVESTMENT_TRANSACTION = (
    3000, date(2024, 1, 10), None, None, "RSU grant", Decimal("147.12"),
    "Vanguard Total Stock Market Index", "1", Decimal("8.0"), Decimal("18.39"),
)


def test_cash_account_has_payee_and_category_fields(qapp, conn):
    dialog = AddRecordDialog(conn, account_id=1, account_type="0", parent=None)
    assert hasattr(dialog, "payee_edit")
    assert hasattr(dialog, "category_edit")
    assert not hasattr(dialog, "security_edit")


def test_investment_account_has_security_and_activity_fields(qapp, conn):
    dialog = AddRecordDialog(conn, account_id=3, account_type="5", parent=None)
    assert hasattr(dialog, "security_edit")
    assert hasattr(dialog, "activity_combo")
    assert not hasattr(dialog, "payee_edit")


def test_ok_button_disabled_until_amount_is_valid(qapp, conn):
    dialog = AddRecordDialog(conn, account_id=1, account_type="0", parent=None)
    ok_button = dialog.button_box.button(QDialogButtonBox.Ok)
    assert not ok_button.isEnabled()
    dialog.amount_edit.setText("-12.50")
    assert ok_button.isEnabled()


def test_ok_button_disabled_for_investment_until_all_fields_valid(qapp, conn):
    dialog = AddRecordDialog(conn, account_id=3, account_type="5", parent=None)
    ok_button = dialog.button_box.button(QDialogButtonBox.Ok)
    dialog.amount_edit.setText("100.00")
    assert not ok_button.isEnabled()  # security/quantity/price still blank
    dialog.security_edit.setText("New Fund")
    dialog.quantity_edit.setText("5")
    dialog.price_edit.setText("20.00")
    assert ok_button.isEnabled()


def test_accept_adds_transaction_and_closes_dialog(qapp, conn):
    dialog = AddRecordDialog(conn, account_id=1, account_type="0", parent=None)
    dialog.date_edit.setDate(QDate(2024, 4, 1))
    dialog.amount_edit.setText("-9.00")
    dialog.payee_edit.setText("New Cafe")
    dialog.category_edit.setText("Dining")

    dialog._on_accept()

    assert dialog.result() == QDialog.Accepted
    assert dialog.transaction_id is not None
    row = conn.execute(
        "SELECT amount FROM transactions WHERE transaction_id = ?", [dialog.transaction_id]
    ).fetchone()
    assert row == (Decimal("-9.00"),)


def test_write_failure_shows_error_and_keeps_dialog_open(qapp, conn, monkeypatch):
    import writes

    def failing_add_transaction(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(writes, "add_transaction", failing_add_transaction)

    dialog = AddRecordDialog(conn, account_id=1, account_type="0", parent=None)
    dialog.amount_edit.setText("-9.00")

    dialog._on_accept()

    assert dialog.result() != QDialog.Accepted
    assert "boom" in dialog.error_label.text()


def test_edit_mode_has_edit_record_title(qapp, conn):
    dialog = AddRecordDialog(
        conn, account_id=1, account_type="0", transaction=CASH_TRANSACTION, parent=None
    )
    assert dialog.windowTitle() == "Edit Record"


def test_edit_mode_prefills_cash_fields_from_existing_transaction(qapp, conn):
    dialog = AddRecordDialog(
        conn, account_id=1, account_type="0", transaction=CASH_TRANSACTION, parent=None
    )
    assert dialog.date_edit.date() == QDate(2024, 3, 15)
    assert dialog.amount_edit.text() == "-52.30"
    assert dialog.memo_edit.text() == "weekly shop"
    assert dialog.payee_edit.text() == "Store A"
    assert dialog.category_edit.text() == "Groceries"


def test_edit_mode_prefills_investment_fields_from_existing_transaction(qapp, conn):
    dialog = AddRecordDialog(
        conn, account_id=3, account_type="5", transaction=INVESTMENT_TRANSACTION, parent=None
    )
    assert dialog.security_edit.text() == "Vanguard Total Stock Market Index"
    assert dialog.activity_combo.currentData() == "1"
    assert dialog.quantity_edit.text() == "8.0"
    assert dialog.price_edit.text() == "18.39"


def test_edit_mode_ok_button_starts_enabled(qapp, conn):
    dialog = AddRecordDialog(
        conn, account_id=1, account_type="0", transaction=CASH_TRANSACTION, parent=None
    )
    assert dialog.button_box.button(QDialogButtonBox.Ok).isEnabled()


def test_accept_updates_existing_transaction_and_closes_dialog(qapp, conn):
    dialog = AddRecordDialog(
        conn, account_id=1, account_type="0", transaction=CASH_TRANSACTION, parent=None
    )
    dialog.amount_edit.setText("-99.00")
    dialog.memo_edit.setText("corrected")

    dialog._on_accept()

    assert dialog.result() == QDialog.Accepted
    assert dialog.transaction_id == 1000
    row = conn.execute(
        "SELECT amount, memo FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    assert row == (Decimal("-99.00"), "corrected")


def test_edit_write_failure_shows_error_and_keeps_dialog_open(qapp, conn, monkeypatch):
    import writes

    def failing_update_transaction(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(writes, "update_transaction", failing_update_transaction)

    dialog = AddRecordDialog(
        conn, account_id=1, account_type="0", transaction=CASH_TRANSACTION, parent=None
    )

    dialog._on_accept()

    assert dialog.result() != QDialog.Accepted
    assert "boom" in dialog.error_label.text()
