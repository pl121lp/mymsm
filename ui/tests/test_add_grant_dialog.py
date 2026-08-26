from datetime import date

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDialog, QDialogButtonBox

from add_grant_dialog import AddGrantDialog


def test_dialog_has_expected_fields(qapp, conn):
    dialog = AddGrantDialog(conn, account_id=3, parent=None)
    assert hasattr(dialog, "security_edit")
    assert hasattr(dialog, "date_edit")
    assert hasattr(dialog, "total_shares_spin")
    assert hasattr(dialog, "frequency_combo")
    assert hasattr(dialog, "vest_count_spin")


def test_defaults_match_the_common_quarterly_three_year_schedule(qapp, conn):
    dialog = AddGrantDialog(conn, account_id=3, parent=None)
    assert dialog.date_edit.date() == QDate.currentDate()
    assert dialog.frequency_combo.currentText() == "Quarter"
    assert dialog.frequency_combo.currentData() == 3
    assert dialog.vest_count_spin.value() == 12


def test_ok_button_disabled_until_grant_name_entered(qapp, conn):
    dialog = AddGrantDialog(conn, account_id=3, parent=None)
    ok_button = dialog.button_box.button(QDialogButtonBox.Ok)
    assert not ok_button.isEnabled()
    dialog.security_edit.setText("2025 New Grant")
    assert ok_button.isEnabled()


def test_accept_creates_grant_and_vest_rows_and_closes_dialog(qapp, conn):
    dialog = AddGrantDialog(conn, account_id=3, parent=None)
    dialog.security_edit.setText("2025 New Grant")
    dialog.date_edit.setDate(QDate(2024, 1, 1))
    dialog.total_shares_spin.setValue(1200)
    dialog.vest_count_spin.setValue(4)

    dialog._on_accept()

    assert dialog.result() == QDialog.Accepted
    assert len(dialog.transaction_ids) == 5  # 1 grant + 4 vests
    rows = conn.execute(
        "SELECT t.txn_date, t.activity, t.quantity FROM transactions t "
        "JOIN securities sec ON sec.security_id = t.security_id "
        "WHERE sec.name = '2025 New Grant' ORDER BY t.txn_date"
    ).fetchall()
    assert rows[0][1] == "17"
    assert rows[0][0] == date(2024, 1, 1)
    assert [r[1] for r in rows[1:]] == ["18", "18", "18", "18"]
    assert [r[0] for r in rows[1:]] == [
        date(2024, 4, 1), date(2024, 7, 1), date(2024, 10, 1), date(2025, 1, 1),
    ]


def test_write_failure_shows_error_and_keeps_dialog_open(qapp, conn, monkeypatch):
    import writes

    def failing_add_rsu_grant(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(writes, "add_rsu_grant", failing_add_rsu_grant)

    dialog = AddGrantDialog(conn, account_id=3, parent=None)
    dialog.security_edit.setText("2025 New Grant")

    dialog._on_accept()

    assert dialog.result() != QDialog.Accepted
    assert "boom" in dialog.error_label.text()
