from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt

from models import (
    AccountTableModel,
    CategoryTransactionTableModel,
    DictionaryListModel,
    SearchResultTableModel,
    SpendingByCategoryTableModel,
    TransactionTableModel,
    activity_label,
    compute_account_value_history,
    compute_net_worth_series,
    compute_spending_by_category,
    generate_sample_dates,
)


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


def test_transaction_at_returns_full_row_tuple():
    model = TransactionTableModel([NON_INVESTMENT_ROW])
    assert model.transaction_at(0) == NON_INVESTMENT_ROW


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


def test_category_transaction_model_shows_date_and_account():
    model = CategoryTransactionTableModel(
        [(1000, date(2024, 3, 15), "Checking", "Store A", "weekly shop", Decimal("-52.30"))]
    )
    assert _data(model, 0, 0) == "2024-03-15"
    assert _data(model, 0, 1) == "Checking"


def test_category_transaction_model_formats_amount():
    model = CategoryTransactionTableModel(
        [(1000, date(2024, 3, 15), "Checking", "Store A", "weekly shop", Decimal("-52.30"))]
    )
    assert _data(model, 0, 4) == "-52.30"


def test_category_transaction_model_handles_missing_payee_and_memo():
    model = CategoryTransactionTableModel(
        [(1002, date(2024, 3, 1), "Checking", None, None, Decimal("-75.00"))]
    )
    assert _data(model, 0, 2) == ""
    assert _data(model, 0, 3) == ""


def test_compute_account_value_history_cash_account_runs_cumulative_balance():
    rows = [
        (1, date(2024, 1, 1), None, None, None, Decimal("50.00"), None, None, None, None),
        (2, date(2024, 1, 2), None, None, None, Decimal("-20.00"), None, None, None, None),
    ]
    history = compute_account_value_history(rows, Decimal("100.00"), is_investment=False)
    assert history == [
        (date(2024, 1, 1), Decimal("150.00")),
        (date(2024, 1, 2), Decimal("130.00")),
    ]


def test_compute_account_value_history_cash_account_sorts_by_date():
    rows = [
        (2, date(2024, 1, 2), None, None, None, Decimal("-20.00"), None, None, None, None),
        (1, date(2024, 1, 1), None, None, None, Decimal("50.00"), None, None, None, None),
    ]
    history = compute_account_value_history(rows, Decimal("0.00"), is_investment=False)
    assert [d for d, _ in history] == [date(2024, 1, 1), date(2024, 1, 2)]


def test_compute_account_value_history_cash_account_defaults_missing_opening_balance_to_zero():
    rows = [(1, date(2024, 1, 1), None, None, None, Decimal("10.00"), None, None, None, None)]
    history = compute_account_value_history(rows, None, is_investment=False)
    assert history == [(date(2024, 1, 1), Decimal("10.00"))]


def test_compute_account_value_history_empty_transactions_returns_empty_list():
    assert compute_account_value_history([], Decimal("100.00"), is_investment=False) == []


def test_compute_account_value_history_investment_account_values_holdings_over_time():
    rows = [
        (1, date(2024, 1, 10), None, None, None, Decimal("147.12"),
         "Fund A", "1", Decimal("8.0"), Decimal("18.39")),
        (2, date(2024, 2, 10), None, None, None, Decimal("64.62"),
         "Fund A", "1", Decimal("3.0"), Decimal("21.54")),
        (3, date(2024, 3, 1), None, None, None, Decimal("-22.63"),
         "Fund A", "2", Decimal("1.0"), Decimal("22.63")),
    ]
    history = compute_account_value_history(rows, Decimal("0.00"), is_investment=True)
    assert history == [
        (date(2024, 1, 10), Decimal("147.12")),  # 8.0 * 18.39
        (date(2024, 2, 10), Decimal("236.94")),  # 11.0 * 21.54
        (date(2024, 3, 1), Decimal("226.30")),   # 10.0 * 22.63
    ]


def test_compute_account_value_history_investment_account_sums_across_securities():
    rows = [
        (1, date(2024, 1, 15), None, None, None, Decimal("200.00"),
         "Fund A", "1", Decimal("10.0"), Decimal("20.00")),
        (2, date(2024, 2, 20), None, None, None, Decimal("64.62"),
         "Fund B", "1", Decimal("3.0"), Decimal("21.54")),
    ]
    history = compute_account_value_history(rows, Decimal("0.00"), is_investment=True)
    assert history == [
        (date(2024, 1, 15), Decimal("200.00")),
        (date(2024, 2, 20), Decimal("264.62")),
    ]


def test_compute_account_value_history_investment_account_ignores_non_trade_activity():
    rows = [
        (1, date(2024, 1, 10), None, None, None, Decimal("147.12"),
         "Fund A", "1", Decimal("8.0"), Decimal("18.39")),
        (2, date(2024, 1, 20), None, None, "RSU grant", Decimal("0.00"),
         "Fund A", "17", Decimal("5.0"), Decimal("100.00")),
    ]
    history = compute_account_value_history(rows, Decimal("0.00"), is_investment=True)
    assert history == [(date(2024, 1, 10), Decimal("147.12"))]


SEARCH_ROW = (
    1000, date(2024, 3, 15), 1, "Checking", "Bank",
    "Store A", "Groceries", "weekly shop", Decimal("-52.30"),
    None, None, None, None,
)

SEARCH_INVESTMENT_ROW = (
    3000, date(2024, 1, 10), 3, "Brokerage A", "5",
    None, None, None, Decimal("147.12"),
    "Vanguard Total Stock Market Index", "1", Decimal("8.0"), Decimal("18.39"),
)


def test_search_result_model_columns_are_date_account_payee_category_investment_memo_amount():
    model = SearchResultTableModel([SEARCH_ROW])
    assert [
        model.headerData(i, Qt.Horizontal) for i in range(model.columnCount())
    ] == ["Date", "Account", "Payee", "Category", "Investment", "Memo", "Amount"]


def test_search_result_model_displays_row_fields():
    model = SearchResultTableModel([SEARCH_ROW])
    assert _data(model, 0, 0) == "2024-03-15"
    assert _data(model, 0, 1) == "Checking"
    assert _data(model, 0, 2) == "Store A"
    assert _data(model, 0, 3) == "Groceries"
    assert _data(model, 0, 4) == ""
    assert _data(model, 0, 5) == "weekly shop"
    assert _data(model, 0, 6) == "-52.30"


def test_search_result_model_displays_investment_name():
    model = SearchResultTableModel([SEARCH_INVESTMENT_ROW])
    assert _data(model, 0, 4) == "Vanguard Total Stock Market Index"


def test_search_result_model_row_count():
    model = SearchResultTableModel([SEARCH_ROW, SEARCH_INVESTMENT_ROW])
    assert model.rowCount() == 2


def test_search_result_model_account_info_at_returns_id_and_type():
    model = SearchResultTableModel([SEARCH_ROW])
    assert model.account_info_at(0) == (1, "Bank")


def test_search_result_model_transaction_at_returns_add_record_dialog_shape():
    model = SearchResultTableModel([SEARCH_ROW])
    assert model.transaction_at(0) == (
        1000, date(2024, 3, 15), "Store A", "Groceries", "weekly shop",
        Decimal("-52.30"), None, None, None, None,
    )


def test_category_transaction_model_row_and_column_count():
    model = CategoryTransactionTableModel(
        [(1000, date(2024, 3, 15), "Checking", "Store A", "weekly shop", Decimal("-52.30"))]
    )
    assert model.rowCount() == 1
    assert model.columnCount() == 5


def test_generate_sample_dates_steps_by_three_months():
    dates = generate_sample_dates(date(2024, 1, 10), date(2024, 10, 10))
    assert dates == [
        date(2024, 1, 10),
        date(2024, 4, 10),
        date(2024, 7, 10),
        date(2024, 10, 10),
    ]


def test_generate_sample_dates_includes_latest_even_if_not_aligned():
    dates = generate_sample_dates(date(2024, 1, 1), date(2024, 8, 15))
    assert dates == [
        date(2024, 1, 1),
        date(2024, 4, 1),
        date(2024, 7, 1),
        date(2024, 8, 15),
    ]


def test_generate_sample_dates_single_point_when_earliest_equals_latest():
    assert generate_sample_dates(date(2024, 1, 1), date(2024, 1, 1)) == [date(2024, 1, 1)]


def test_generate_sample_dates_clamps_month_end_overflow():
    # Jan 31 + 3 months has no day 31 in April, so it should clamp to Apr 30.
    dates = generate_sample_dates(date(2024, 1, 31), date(2024, 4, 30))
    assert dates == [date(2024, 1, 31), date(2024, 4, 30)]


def test_compute_net_worth_series_uses_initial_value_before_first_transaction():
    accounts = [
        ("USD", Decimal("100"), [(date(2024, 1, 15), Decimal("150"))]),
        ("SEK", Decimal("0"), [(date(2024, 1, 10), Decimal("1000"))]),
    ]

    def to_usd(currency, amount):
        return amount if currency == "USD" else amount * Decimal("0.1")

    series = compute_net_worth_series(accounts, [date(2024, 1, 1)], to_usd)
    assert series == [(date(2024, 1, 1), Decimal("100"))]


def test_compute_net_worth_series_sums_accounts_converted_to_usd_as_of_each_date():
    accounts = [
        ("USD", Decimal("100"), [(date(2024, 1, 15), Decimal("150"))]),
        ("SEK", Decimal("0"), [(date(2024, 1, 10), Decimal("1000"))]),
    ]

    def to_usd(currency, amount):
        return amount if currency == "USD" else amount * Decimal("0.1")

    series = compute_net_worth_series(accounts, [date(2024, 1, 1), date(2024, 2, 1)], to_usd)
    assert series == [
        (date(2024, 1, 1), Decimal("100")),
        (date(2024, 2, 1), Decimal("250")),
    ]


def test_compute_net_worth_series_holds_last_value_flat_after_final_transaction():
    accounts = [("USD", Decimal("0"), [(date(2024, 1, 10), Decimal("500"))])]
    series = compute_net_worth_series(
        accounts, [date(2024, 6, 1)], to_usd=lambda currency, amount: amount
    )
    assert series == [(date(2024, 6, 1), Decimal("500"))]


def test_compute_spending_by_category_sorts_highest_spending_first():
    transactions = [
        (10, "Utilities", date(2024, 3, 1), Decimal("-75.00"), "USD"),
        (20, "Groceries", date(2024, 3, 10), Decimal("-20.00"), "USD"),
        (20, "Groceries", date(2024, 3, 15), Decimal("-52.30"), "USD"),
    ]
    result = compute_spending_by_category(
        transactions, date(2024, 1, 1), date(2024, 12, 31), to_usd=lambda currency, amount: amount
    )
    assert result == [
        ("Utilities", Decimal("75.00")),
        ("Groceries", Decimal("72.30")),
    ]


def test_compute_spending_by_category_ignores_positive_amounts():
    transactions = [
        (10, "Utilities", date(2024, 3, 1), Decimal("-75.00"), "USD"),
        (20, "Groceries", date(2024, 3, 5), Decimal("30.00"), "USD"),
    ]
    result = compute_spending_by_category(
        transactions, date(2024, 1, 1), date(2024, 12, 31), to_usd=lambda currency, amount: amount
    )
    assert result == [("Utilities", Decimal("75.00"))]


def test_compute_spending_by_category_filters_to_date_range():
    transactions = [
        (10, "Utilities", date(2024, 1, 1), Decimal("-75.00"), "USD"),
        (20, "Groceries", date(2024, 6, 1), Decimal("-20.00"), "USD"),
    ]
    result = compute_spending_by_category(
        transactions, date(2024, 5, 1), date(2024, 12, 31), to_usd=lambda currency, amount: amount
    )
    assert result == [("Groceries", Decimal("20.00"))]


def test_compute_spending_by_category_converts_currency():
    transactions = [(10, "Travel", date(2024, 3, 1), Decimal("-100.00"), "SEK")]
    result = compute_spending_by_category(
        transactions,
        date(2024, 1, 1),
        date(2024, 12, 31),
        to_usd=lambda currency, amount: amount * Decimal("0.1"),
    )
    assert result == [("Travel", Decimal("10.000"))]


def test_compute_spending_by_category_empty_transactions_returns_empty_list():
    assert compute_spending_by_category([], date(2024, 1, 1), date(2024, 12, 31), lambda c, a: a) == []


def test_spending_by_category_model_columns_are_category_and_spending():
    model = SpendingByCategoryTableModel([("Groceries", Decimal("72.30"))])
    assert model.rowCount() == 1
    assert model.columnCount() == 2
    assert _data(model, 0, 0) == "Groceries"
    assert _data(model, 0, 1) == "72.30"


def test_spending_by_category_model_set_categories_replaces_contents():
    model = SpendingByCategoryTableModel()
    assert model.rowCount() == 0
    model.set_categories([("Utilities", Decimal("75.00"))])
    assert model.rowCount() == 1
    assert _data(model, 0, 0) == "Utilities"
