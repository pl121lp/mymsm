from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QDialog, QDialogButtonBox

from summarize_dialog import SummarizeDialog


def _txn(transaction_id, txn_date, payee, amount):
    return (transaction_id, txn_date, payee, "Category", "memo", amount, None, None, None, None)


def test_dialog_shows_summary_stats(qapp):
    transactions = [
        _txn(1000, date(2024, 3, 15), "Store A", Decimal("-52.30")),
        _txn(1001, date(2024, 3, 10), "Store B", Decimal("-20.00")),
        _txn(1002, date(2024, 3, 20), "Store A", Decimal("100.00")),
    ]

    dialog = SummarizeDialog(transactions)

    assert dialog.windowTitle() == "Summarize Records"
    assert dialog.payees_label.text() == "Payees: Store A, Store B"
    assert dialog.date_range_label.text() == "Date range: 2024-03-10 – 2024-03-20"
    assert dialog.count_label.text() == "3 records"
    assert dialog.total_label.text() == "Total: 27.70"
    assert dialog.average_label.text() == "Average: 9.23"


def test_dialog_omits_missing_payees_from_list(qapp):
    transactions = [
        _txn(1000, date(2024, 3, 15), "Store A", Decimal("-52.30")),
        _txn(1001, date(2024, 3, 10), None, Decimal("1000.00")),
    ]

    dialog = SummarizeDialog(transactions)

    assert dialog.payees_label.text() == "Payees: Store A"


def test_dialog_has_ok_button_only_and_accepts(qapp):
    transactions = [_txn(1000, date(2024, 1, 1), "Store A", Decimal("10.00"))]

    dialog = SummarizeDialog(transactions)

    assert dialog.button_box.standardButtons() == QDialogButtonBox.Ok
    dialog.button_box.accepted.emit()
    assert dialog.result() == QDialog.Accepted
