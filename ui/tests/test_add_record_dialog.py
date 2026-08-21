from decimal import Decimal

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDialog, QDialogButtonBox

from add_record_dialog import AddRecordDialog


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
