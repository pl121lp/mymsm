from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QDialog, QDialogButtonBox

from import_qfx_dialog import ImportQfxDialog
from qfx_import import QfxRecord


def _record(name="New Payee", amount="-10.00", txn_date=date(2024, 4, 1), memo="a memo"):
    return QfxRecord(
        trn_type="DEBIT", txn_date=txn_date, amount=Decimal(amount),
        fitid="1", name=name, memo=memo, checknum="",
    )


def test_lists_open_accounts_in_selector(qapp, conn):
    # conn fixture: account 1 Checking (open), 2 Old Card (closed), 3 Brokerage (open).
    dialog = ImportQfxDialog(conn, records=[], parent=None)
    account_ids = {dialog.account_combo.itemData(i) for i in range(dialog.account_combo.count())}
    assert account_ids == {1, 3}


def test_preselects_default_account_when_given(qapp, conn):
    dialog = ImportQfxDialog(conn, records=[], default_account_id=3, parent=None)
    assert dialog.account_combo.currentData() == 3


def test_all_records_go_to_import_table_when_no_existing_match(qapp, conn):
    records = [_record(name="Brand New Payee", amount="-42.00", txn_date=date(2024, 4, 1))]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)
    assert dialog.import_table.rowCount() == 1
    assert dialog.duplicates_table.rowCount() == 0


def test_record_matching_existing_transaction_is_flagged_as_duplicate(qapp, conn):
    # conn fixture seeds transaction_id 1000 on account 1: 2024-03-15, -52.30, payee "Store A".
    records = [_record(name="Store A", amount="-52.30", txn_date=date(2024, 3, 15))]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)
    assert dialog.import_table.rowCount() == 0
    assert dialog.duplicates_table.rowCount() == 1


def test_duplicate_match_requires_name_amount_and_date_together(qapp, conn):
    records = [
        _record(name="Store A", amount="-52.30", txn_date=date(2024, 3, 16)),  # date differs
        _record(name="Store A", amount="-1.00", txn_date=date(2024, 3, 15)),  # amount differs
        _record(name="Someone Else", amount="-52.30", txn_date=date(2024, 3, 15)),  # name differs
    ]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)
    assert dialog.import_table.rowCount() == 3
    assert dialog.duplicates_table.rowCount() == 0


def test_changing_account_recomputes_duplicate_split(qapp, conn):
    records = [_record(name="Store A", amount="-52.30", txn_date=date(2024, 3, 15))]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=3, parent=None)
    assert dialog.import_table.rowCount() == 1  # account 3 has no such transaction

    index = dialog.account_combo.findData(1)
    dialog.account_combo.setCurrentIndex(index)

    assert dialog.import_table.rowCount() == 0
    assert dialog.duplicates_table.rowCount() == 1


def test_apply_button_disabled_when_nothing_to_import(qapp, conn):
    records = [_record(name="Store A", amount="-52.30", txn_date=date(2024, 3, 15))]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)
    assert not dialog.apply_button.isEnabled()


def test_apply_inserts_only_non_duplicate_records_and_accepts(qapp, conn):
    records = [
        _record(name="Store A", amount="-52.30", txn_date=date(2024, 3, 15)),  # duplicate
        _record(name="Brand New Payee", amount="-42.00", txn_date=date(2024, 4, 1)),  # new
    ]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)

    dialog._on_apply()

    assert dialog.result() == QDialog.Accepted
    assert dialog.imported_count == 1
    assert len(dialog.imported_transaction_ids) == 1
    row = conn.execute(
        "SELECT p.name, t.amount FROM transactions t JOIN payees p ON p.payee_id = t.payee_id "
        "WHERE t.account_id = 1 AND t.txn_date = '2024-04-01'"
    ).fetchone()
    assert row == ("Brand New Payee", Decimal("-42.00"))


def test_discard_button_makes_no_database_changes(qapp, conn):
    records = [_record(name="Brand New Payee", amount="-42.00", txn_date=date(2024, 4, 1))]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)

    dialog.discard_button.click()

    assert dialog.result() == QDialog.Rejected
    row = conn.execute(
        "SELECT transaction_id FROM transactions WHERE account_id = 1 AND txn_date = '2024-04-01'"
    ).fetchone()
    assert row is None


def test_import_table_is_sorted_by_date_descending(qapp, conn):
    records = [
        _record(name="Older", amount="-1.00", txn_date=date(2024, 3, 1)),
        _record(name="Newest", amount="-2.00", txn_date=date(2024, 4, 15)),
        _record(name="Middle", amount="-3.00", txn_date=date(2024, 4, 1)),
    ]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)
    names = [dialog.import_table.item(row, 3).text() for row in range(3)]
    assert names == ["Newest", "Middle", "Older"]


def test_moving_a_row_keeps_destination_table_sorted_by_date(qapp, conn):
    records = [
        _record(name="Older", amount="-1.00", txn_date=date(2024, 3, 1)),
        _record(name="Newest", amount="-2.00", txn_date=date(2024, 4, 15)),
    ]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)
    # "Older" is row 1 in the sorted import table (Newest, Older).
    dialog.import_table.cellDoubleClicked.emit(1, 0)

    # Now move "Newest" too, so duplicates_table gets both, out of insertion order.
    dialog.import_table.cellDoubleClicked.emit(0, 0)

    names = [dialog.duplicates_table.item(row, 3).text() for row in range(2)]
    assert names == ["Newest", "Older"]


def test_double_clicking_import_row_moves_it_to_duplicates(qapp, conn):
    records = [_record(name="Brand New Payee", amount="-42.00", txn_date=date(2024, 4, 1))]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)
    assert dialog.import_table.rowCount() == 1

    dialog.import_table.cellDoubleClicked.emit(0, 0)

    assert dialog.import_table.rowCount() == 0
    assert dialog.duplicates_table.rowCount() == 1
    assert dialog.duplicates_table.item(0, 3).text() == "Brand New Payee"
    assert dialog._to_import == []
    assert dialog._duplicates == records


def test_double_clicking_duplicate_row_moves_it_to_import(qapp, conn):
    # conn fixture seeds transaction_id 1000 on account 1: 2024-03-15, -52.30, payee "Store A".
    records = [_record(name="Store A", amount="-52.30", txn_date=date(2024, 3, 15))]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)
    assert dialog.duplicates_table.rowCount() == 1

    dialog.duplicates_table.cellDoubleClicked.emit(0, 0)

    assert dialog.duplicates_table.rowCount() == 0
    assert dialog.import_table.rowCount() == 1
    assert dialog._to_import == records
    assert dialog._duplicates == []


def test_moving_last_import_row_to_duplicates_disables_apply(qapp, conn):
    records = [_record(name="Brand New Payee", amount="-42.00", txn_date=date(2024, 4, 1))]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)
    assert dialog.apply_button.isEnabled()

    dialog.import_table.cellDoubleClicked.emit(0, 0)

    assert not dialog.apply_button.isEnabled()


def test_moving_duplicate_row_to_import_enables_apply(qapp, conn):
    records = [_record(name="Store A", amount="-52.30", txn_date=date(2024, 3, 15))]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)
    assert not dialog.apply_button.isEnabled()

    dialog.duplicates_table.cellDoubleClicked.emit(0, 0)

    assert dialog.apply_button.isEnabled()


def test_context_menu_move_action_moves_import_row_to_duplicates(qapp, conn, monkeypatch):
    import import_qfx_dialog

    records = [_record(name="Brand New Payee", amount="-42.00", txn_date=date(2024, 4, 1))]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)

    captured_actions = []

    class FakeMenu:
        def __init__(self, parent=None):
            pass

        def addAction(self, text):
            captured_actions.append(text)
            return text

        def exec(self, pos):
            return "Move"

    monkeypatch.setattr(import_qfx_dialog, "QMenu", FakeMenu)

    from PySide6.QtCore import QPoint

    dialog._show_move_menu(QPoint(0, 5), dialog.import_table, dialog._to_import, dialog._duplicates)

    assert captured_actions == ["Move"]
    assert dialog.import_table.rowCount() == 0
    assert dialog.duplicates_table.rowCount() == 1


def test_context_menu_move_action_moves_all_selected_rows(qapp, conn, monkeypatch):
    import import_qfx_dialog
    from PySide6.QtCore import QPoint
    from PySide6.QtWidgets import QTableWidgetSelectionRange

    records = [
        _record(name="Payee A", amount="-1.00", txn_date=date(2024, 4, 1)),
        _record(name="Payee B", amount="-2.00", txn_date=date(2024, 4, 2)),
        _record(name="Payee C", amount="-3.00", txn_date=date(2024, 4, 3)),
    ]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)
    assert dialog.import_table.rowCount() == 3

    # Select two of the three rows (rows sorted newest-first: C, B, A).
    dialog.import_table.setRangeSelected(
        QTableWidgetSelectionRange(0, 0, 1, dialog.import_table.columnCount() - 1), True
    )

    captured_actions = []

    class FakeMenu:
        def __init__(self, parent=None):
            pass

        def addAction(self, text):
            captured_actions.append(text)
            return text

        def exec(self, pos):
            return "Move"

    monkeypatch.setattr(import_qfx_dialog, "QMenu", FakeMenu)

    dialog._show_move_menu(QPoint(0, 0), dialog.import_table, dialog._to_import, dialog._duplicates)

    assert dialog.import_table.rowCount() == 1
    assert dialog.duplicates_table.rowCount() == 2
    remaining_names = [dialog.import_table.item(0, 3).text()]
    assert remaining_names == ["Payee A"]


def test_context_menu_at_empty_row_does_nothing(qapp, conn):
    from PySide6.QtCore import QPoint

    records = [_record(name="Brand New Payee", amount="-42.00", txn_date=date(2024, 4, 1))]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)

    dialog._show_move_menu(
        QPoint(0, 9999), dialog.import_table, dialog._to_import, dialog._duplicates
    )

    assert dialog.import_table.rowCount() == 1
    assert dialog.duplicates_table.rowCount() == 0


def test_write_failure_on_apply_shows_error_and_keeps_dialog_open(qapp, conn, monkeypatch):
    import import_qfx_dialog

    def failing_import(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(import_qfx_dialog.writes, "import_transactions", failing_import)

    records = [_record(name="Brand New Payee", amount="-42.00", txn_date=date(2024, 4, 1))]
    dialog = ImportQfxDialog(conn, records=records, default_account_id=1, parent=None)

    dialog._on_apply()

    assert dialog.result() != QDialog.Accepted
    assert "boom" in dialog.error_label.text()
