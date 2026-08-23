from datetime import date
from decimal import Decimal

from category_transactions_dialog import CategoryTransactionsDialog


def test_dialog_shows_title_and_row_count(qapp):
    transactions = [
        (1000, date(2024, 3, 15), "Checking", "Store A", "weekly shop", Decimal("-52.30")),
        (1001, date(2024, 3, 10), "Savings", "Store B", "snacks", Decimal("-20.00")),
    ]
    dialog = CategoryTransactionsDialog("Groceries", transactions)

    assert dialog.windowTitle() == "Transactions: Groceries"
    assert dialog.count_label.text() == "2 records"
    assert dialog.table_view.model().rowCount() == 2


def test_dialog_with_no_transactions_shows_zero_records(qapp):
    dialog = CategoryTransactionsDialog("Utilities", [])

    assert dialog.count_label.text() == "0 records"
    assert dialog.table_view.model().rowCount() == 0
