from datetime import date
from decimal import Decimal

from PySide6.QtCore import QAbstractListModel, Qt

from models import AccountTableModel, DictionaryListModel, TransactionTableModel, activity_label


def _data(model, row, col):
    return model.data(model.index(row, col), Qt.DisplayRole)


def test_account_type_is_translated_to_label():
    model = AccountTableModel([(1, "Checking", "0", "USD", Decimal("100.00"), False)])
    assert _data(model, 0, 1) == "Checking/Savings"


def test_unknown_account_type_falls_back_to_raw_value():
    model = AccountTableModel([(1, "Mystery", "42", "USD", Decimal("0"), False)])
    assert _data(model, 0, 1) == "Type 42"


def test_currency_column_shows_account_currency():
    model = AccountTableModel([(1, "Savings", "0", "SEK", Decimal("100.00"), False)])
    assert _data(model, 0, 2) == "SEK"


def test_balance_column_is_formatted_as_currency():
    model = AccountTableModel([(1, "Checking", "0", "USD", Decimal("1047.70"), False)])
    assert _data(model, 0, 3) == "1,047.70"


def test_negative_balance_is_formatted_as_currency():
    model = AccountTableModel([(1, "Credit Card", "1", "USD", Decimal("-918.98"), False)])
    assert _data(model, 0, 3) == "-918.98"


def test_usd_balance_is_unaffected_by_exchange_rate():
    model = AccountTableModel([(1, "Checking", "0", "USD", Decimal("100.00"), False)])
    model.set_exchange_rates({"SEK": Decimal("0.10")})
    assert _data(model, 0, 3) == "100.00"


def test_non_usd_balance_is_converted_using_exchange_rate():
    model = AccountTableModel([(1, "Savings", "0", "SEK", Decimal("1000.00"), False)])
    model.set_exchange_rates({"SEK": Decimal("0.10")})
    assert _data(model, 0, 3) == "100.00"


def test_non_usd_balance_is_unconverted_when_no_rate_known():
    model = AccountTableModel([(1, "Savings", "0", "SEK", Decimal("1000.00"), False)])
    assert _data(model, 0, 3) == "1,000.00"


def test_total_usd_sums_converted_balances():
    model = AccountTableModel([
        (1, "Checking", "0", "USD", Decimal("100.00"), False),
        (2, "Savings", "0", "SEK", Decimal("1000.00"), False),
    ])
    model.set_exchange_rates({"SEK": Decimal("0.10")})
    assert model.total_usd() == Decimal("200.00")


def test_total_usd_excludes_closed_accounts():
    model = AccountTableModel([
        (1, "Checking", "0", "USD", Decimal("100.00"), False),
        (2, "Old Card", "1", "USD", Decimal("500.00"), True),
    ])
    assert model.total_usd() == Decimal("100.00")


def test_open_account_name_has_no_prefix():
    model = AccountTableModel([(1, "Checking", "0", "USD", Decimal("100.00"), False)])
    assert _data(model, 0, 0) == "Checking"


def test_closed_account_name_is_prefixed_with_closed():
    model = AccountTableModel([(1, "Old Card", "1", "USD", Decimal("0.00"), True)])
    assert _data(model, 0, 0) == "(CLOSED) Old Card"


def test_activity_buy_and_sell_are_translated_to_labels():
    assert activity_label("1") == "Buy"
    assert activity_label("2") == "Sell"


def test_unknown_activity_falls_back_to_raw_value():
    assert activity_label("17") == "Activity 17"


def test_activity_label_of_none_is_blank():
    assert activity_label(None) == ""


NON_INVESTMENT_ROW = (
    1000, date(2024, 3, 15), "Store A", "Groceries", "weekly shop", Decimal("-52.30"),
    None, None, None, None,
)

INVESTMENT_ROW = (
    2000, date(2024, 2, 1), None, None, None, Decimal("147.12"),
    "Vanguard Total Stock Market Index", "1", Decimal("8.0"), Decimal("18.39"),
)


def test_default_transaction_columns_are_payee_category_memo_amount():
    model = TransactionTableModel([NON_INVESTMENT_ROW])
    assert model.columnCount() == 5
    assert _data(model, 0, 1) == "Store A"
    assert _data(model, 0, 2) == "Groceries"
    assert _data(model, 0, 3) == "weekly shop"
    assert _data(model, 0, 4) == "-52.30"


def test_investment_account_shows_investment_columns():
    model = TransactionTableModel()
    model.set_transactions([INVESTMENT_ROW], is_investment=True)
    assert [
        model.headerData(i, Qt.Horizontal) for i in range(model.columnCount())
    ] == ["Date", "Investment", "Activity", "Quantity", "Price", "Amount", "Memo"]
    assert _data(model, 0, 1) == "Vanguard Total Stock Market Index"
    assert _data(model, 0, 2) == "Buy"
    assert _data(model, 0, 3) == "8.0000"
    assert _data(model, 0, 4) == "18.3900"
    assert _data(model, 0, 5) == "147.12"
    assert _data(model, 0, 6) == ""


def test_investment_row_with_missing_price_displays_blank():
    row = (
        2003, date(2024, 2, 25), None, None, "RSU grant", Decimal("0.00"),
        "Fidelity Contrafund", "17", Decimal("20.0"), None,
    )
    model = TransactionTableModel()
    model.set_transactions([row], is_investment=True)
    assert _data(model, 0, 2) == "Activity 17"
    assert _data(model, 0, 4) == ""


def test_switching_back_to_non_investment_restores_default_columns():
    model = TransactionTableModel()
    model.set_transactions([INVESTMENT_ROW], is_investment=True)
    model.set_transactions([NON_INVESTMENT_ROW], is_investment=False)
    assert model.columnCount() == 5
    assert _data(model, 0, 1) == "Store A"


def test_sort_by_amount_ascending():
    rows = [
        (1, date(2024, 1, 1), "Store A", "Groceries", "m1", Decimal("50.00"), None, None, None, None),
        (2, date(2024, 1, 2), "Store B", "Dining", "m2", Decimal("-20.00"), None, None, None, None),
        (3, date(2024, 1, 3), "Store C", "Rent", "m3", Decimal("10.00"), None, None, None, None),
    ]
    model = TransactionTableModel(rows)
    model.sort(4, Qt.AscendingOrder)
    assert [_data(model, r, 4) for r in range(3)] == ["-20.00", "10.00", "50.00"]


def test_sort_by_amount_descending():
    rows = [
        (1, date(2024, 1, 1), "Store A", "Groceries", "m1", Decimal("50.00"), None, None, None, None),
        (2, date(2024, 1, 2), "Store B", "Dining", "m2", Decimal("-20.00"), None, None, None, None),
        (3, date(2024, 1, 3), "Store C", "Rent", "m3", Decimal("10.00"), None, None, None, None),
    ]
    model = TransactionTableModel(rows)
    model.sort(4, Qt.DescendingOrder)
    assert [_data(model, r, 4) for r in range(3)] == ["50.00", "10.00", "-20.00"]


def test_sort_by_payee_puts_blank_payees_last_regardless_of_direction():
    rows = [
        (1, date(2024, 1, 1), "Store B", "Groceries", "m1", Decimal("1.00"), None, None, None, None),
        (2, date(2024, 1, 2), None, "Dining", "m2", Decimal("2.00"), None, None, None, None),
        (3, date(2024, 1, 3), "Store A", "Rent", "m3", Decimal("3.00"), None, None, None, None),
    ]
    model = TransactionTableModel(rows)

    model.sort(1, Qt.AscendingOrder)
    assert [_data(model, r, 1) for r in range(3)] == ["Store A", "Store B", ""]

    model.sort(1, Qt.DescendingOrder)
    assert [_data(model, r, 1) for r in range(3)] == ["Store B", "Store A", ""]


def test_sort_investment_transactions_by_quantity():
    rows = [
        (1, date(2024, 1, 1), None, None, None, Decimal("1.00"), "Fund A", "1", Decimal("5.0"), Decimal("10.0")),
        (2, date(2024, 1, 2), None, None, None, Decimal("2.00"), "Fund B", "1", Decimal("1.0"), Decimal("20.0")),
    ]
    model = TransactionTableModel()
    model.set_transactions(rows, is_investment=True)
    model.sort(3, Qt.AscendingOrder)
    assert [_data(model, r, 3) for r in range(2)] == ["1.0000", "5.0000"]


def test_dictionary_list_model_shows_name_at_index():
    model = DictionaryListModel([(10, "Utilities"), (20, "Groceries")])
    assert model.data(model.index(0, 0), Qt.DisplayRole) == "Utilities"
    assert model.data(model.index(1, 0), Qt.DisplayRole) == "Groceries"


def test_dictionary_list_model_id_at_returns_id():
    model = DictionaryListModel([(10, "Utilities"), (20, "Groceries")])
    assert model.id_at(0) == 10
    assert model.id_at(1) == 20


def test_dictionary_list_model_row_count():
    model = DictionaryListModel([(10, "Utilities"), (20, "Groceries")])
    assert model.rowCount() == 2


def test_dictionary_list_model_set_items_replaces_contents():
    model = DictionaryListModel([(10, "Utilities")])
    model.set_items([(30, "Entertainment")])
    assert model.rowCount() == 1
    assert model.id_at(0) == 30
