from decimal import Decimal

from PySide6.QtWidgets import QDialog, QDialogButtonBox

from account_details_dialog import AccountDetailsDialog


def _make_dialog(conn, **overrides):
    kwargs = dict(
        conn=conn,
        account_id=1,
        name="Checking",
        account_type_label="Bank",
        currency="USD",
        opening_balance=Decimal("100.00"),
        balance_label="Balance:",
        balance_text="150.00 USD",
        status_text="Open",
        parent=None,
    )
    kwargs.update(overrides)
    return AccountDetailsDialog(**kwargs)


def test_dialog_shows_account_fields(qapp, conn):
    dialog = _make_dialog(conn)

    assert dialog.name_edit.text() == "Checking"
    assert dialog.type_value.text() == "Bank"
    assert dialog.currency_value.text() == "USD"
    assert dialog.opening_balance_edit.text() == "100.00"
    assert dialog.balance_label.text() == "Balance:"
    assert dialog.balance_value.text() == "150.00 USD"
    assert dialog.status_value.text() == "Open"


def test_dialog_shows_qfx_acct_id_when_set(qapp, conn):
    dialog = _make_dialog(conn, qfx_acct_id="597883795")
    assert dialog.qfx_acct_id_edit.text() == "597883795"


def test_dialog_shows_empty_qfx_acct_id_when_not_set(qapp, conn):
    dialog = _make_dialog(conn, qfx_acct_id=None)
    assert dialog.qfx_acct_id_edit.text() == ""


def test_dialog_uses_value_label_for_investment_accounts(qapp, conn):
    dialog = _make_dialog(conn, balance_label="Value:")

    assert dialog.balance_label.text() == "Value:"


def test_dialog_prefills_zero_when_opening_balance_is_none(qapp, conn):
    dialog = _make_dialog(conn, opening_balance=None)

    assert dialog.opening_balance_edit.text() == "0"


def test_dialog_has_save_and_cancel_buttons(qapp, conn):
    dialog = _make_dialog(conn)

    assert dialog.button_box.standardButtons() == (QDialogButtonBox.Save | QDialogButtonBox.Cancel)


def test_save_button_disabled_when_name_is_blank(qapp, conn):
    dialog = _make_dialog(conn)
    dialog.name_edit.setText("")
    assert not dialog.button_box.button(QDialogButtonBox.Save).isEnabled()


def test_save_button_disabled_when_opening_balance_invalid(qapp, conn):
    dialog = _make_dialog(conn)
    dialog.opening_balance_edit.setText("not-a-number")
    assert not dialog.button_box.button(QDialogButtonBox.Save).isEnabled()


def test_save_button_enabled_with_valid_fields(qapp, conn):
    dialog = _make_dialog(conn)
    assert dialog.button_box.button(QDialogButtonBox.Save).isEnabled()


def test_cancel_rejects_dialog_without_writing(qapp, conn):
    dialog = _make_dialog(conn)
    dialog.name_edit.setText("Changed Name")

    dialog.button_box.button(QDialogButtonBox.Cancel).click()

    assert dialog.result() == QDialog.Rejected
    row = conn.execute("SELECT name FROM accounts WHERE account_id = 1").fetchone()
    assert row == ("Checking",)


def test_save_writes_updated_name_and_balance_and_accepts(qapp, conn):
    dialog = _make_dialog(conn)
    dialog.name_edit.setText("Checking Renamed")
    dialog.opening_balance_edit.setText("250.00")

    dialog._on_accept()

    assert dialog.result() == QDialog.Accepted
    row = conn.execute(
        "SELECT name, opening_balance FROM accounts WHERE account_id = 1"
    ).fetchone()
    assert row == ("Checking Renamed", Decimal("250.00"))


def test_save_writes_edited_qfx_acct_id(qapp, conn):
    dialog = _make_dialog(conn, qfx_acct_id=None)
    dialog.qfx_acct_id_edit.setText("597883795")

    dialog._on_accept()

    row = conn.execute("SELECT qfx_acct_id FROM accounts WHERE account_id = 1").fetchone()
    assert row == ("597883795",)


def test_save_with_blank_qfx_acct_id_clears_existing_mapping(qapp, conn):
    conn.execute("UPDATE accounts SET qfx_acct_id = '597883795' WHERE account_id = 1")
    dialog = _make_dialog(conn, qfx_acct_id="597883795")
    dialog.qfx_acct_id_edit.setText("")

    dialog._on_accept()

    row = conn.execute("SELECT qfx_acct_id FROM accounts WHERE account_id = 1").fetchone()
    assert row == (None,)
