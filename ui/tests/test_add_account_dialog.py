from decimal import Decimal

from PySide6.QtWidgets import QDialog, QDialogButtonBox

from add_account_dialog import AddAccountDialog


def test_ok_button_disabled_until_name_is_valid(qapp, conn):
    dialog = AddAccountDialog(conn, parent=None)
    ok_button = dialog.button_box.button(QDialogButtonBox.Ok)
    assert not ok_button.isEnabled()
    dialog.name_edit.setText("New Savings")
    assert ok_button.isEnabled()


def test_defaults_currency_to_usd_and_balance_to_zero(qapp, conn):
    dialog = AddAccountDialog(conn, parent=None)
    assert dialog.currency_edit.text() == "USD"
    assert dialog.opening_balance_edit.text() == "0"


def test_ok_button_disabled_when_opening_balance_invalid(qapp, conn):
    dialog = AddAccountDialog(conn, parent=None)
    dialog.name_edit.setText("New Savings")
    dialog.opening_balance_edit.setText("not-a-number")
    assert not dialog.button_box.button(QDialogButtonBox.Ok).isEnabled()


def test_accept_adds_account_and_closes_dialog(qapp, conn):
    dialog = AddAccountDialog(conn, parent=None)
    dialog.name_edit.setText("New Savings")
    dialog.opening_balance_edit.setText("250.00")

    dialog._on_accept()

    assert dialog.result() == QDialog.Accepted
    assert dialog.account_id is not None
    row = conn.execute(
        "SELECT name, opening_balance, currency, is_closed FROM accounts WHERE account_id = ?",
        [dialog.account_id],
    ).fetchone()
    assert row == ("New Savings", Decimal("250.00"), "USD", False)


def test_write_failure_shows_error_and_keeps_dialog_open(qapp, conn, monkeypatch):
    import writes

    def failing_add_account(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(writes, "add_account", failing_add_account)

    dialog = AddAccountDialog(conn, parent=None)
    dialog.name_edit.setText("New Savings")

    dialog._on_accept()

    assert dialog.result() != QDialog.Accepted
    assert "boom" in dialog.error_label.text()
