from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt

import models
import theme
from models import (
    AccountTableModel,
    CategoryTransactionTableModel,
    DictionaryListModel,
    IncomeByCategoryTableModel,
    InvestmentAnalysisTableModel,
    SearchResultTableModel,
    SpendingByCategoryTableModel,
    TransactionTableModel,
    activity_label,
    build_loan_transaction_rows,
    compute_account_value_history,
    compute_income_by_category,
    compute_investment_analysis,
    compute_loan_totals,
    compute_net_worth_series,
    compute_spending_by_category,
    generate_sample_dates,
)


def _data(model, row, col):
    return model.data(model.index(row, col), Qt.DisplayRole)


def test_account_type_is_translated_to_label():
    model = AccountTableModel([(1, "Checking", "0", "USD", Decimal("100.00"), False, False)])
    assert _data(model, 0, 1) == "Checking/Savings"


def test_unknown_account_type_falls_back_to_raw_value():
    model = AccountTableModel([(1, "Mystery", "42", "USD", Decimal("0"), False, False)])
    assert _data(model, 0, 1) == "Type 42"


def test_currency_column_shows_account_currency():
    model = AccountTableModel([(1, "Savings", "0", "SEK", Decimal("100.00"), False, False)])
    assert _data(model, 0, 2) == "SEK"


def test_balance_column_is_formatted_as_currency():
    model = AccountTableModel([(1, "Checking", "0", "USD", Decimal("1047.70"), False, False)])
    assert _data(model, 0, 3) == "1,047.70"


def test_negative_balance_is_formatted_as_currency():
    model = AccountTableModel([(1, "Credit Card", "1", "USD", Decimal("-918.98"), False, False)])
    assert _data(model, 0, 3) == "-918.98"


def test_usd_balance_is_unaffected_by_exchange_rate():
    model = AccountTableModel([(1, "Checking", "0", "USD", Decimal("100.00"), False, False)])
    model.set_exchange_rates({"SEK": Decimal("0.10")})
    assert _data(model, 0, 3) == "100.00"


def test_non_usd_balance_is_converted_using_exchange_rate():
    model = AccountTableModel([(1, "Savings", "0", "SEK", Decimal("1000.00"), False, False)])
    model.set_exchange_rates({"SEK": Decimal("0.10")})
    assert _data(model, 0, 3) == "100.00"


def test_non_usd_balance_is_unconverted_when_no_rate_known():
    model = AccountTableModel([(1, "Savings", "0", "SEK", Decimal("1000.00"), False, False)])
    assert _data(model, 0, 3) == "1,000.00"


def test_total_usd_sums_converted_balances():
    model = AccountTableModel([
        (1, "Checking", "0", "USD", Decimal("100.00"), False, False),
        (2, "Savings", "0", "SEK", Decimal("1000.00"), False, False),
    ])
    model.set_exchange_rates({"SEK": Decimal("0.10")})
    assert model.total_usd() == Decimal("200.00")


def test_total_usd_excludes_closed_accounts():
    model = AccountTableModel([
        (1, "Checking", "0", "USD", Decimal("100.00"), False, False),
        (2, "Old Card", "1", "USD", Decimal("500.00"), True, False),
    ])
    assert model.total_usd() == Decimal("100.00")


def test_account_model_sort_by_name_ascending():
    model = AccountTableModel([
        (1, "Savings", "0", "USD", Decimal("100.00"), False, False),
        (2, "Checking", "0", "USD", Decimal("50.00"), False, False),
    ])
    model.sort(0, Qt.AscendingOrder)
    assert _data(model, 0, 0) == "Checking"
    assert _data(model, 1, 0) == "Savings"


def test_account_model_sort_by_name_is_case_insensitive():
    model = AccountTableModel([
        (1, "savings", "0", "USD", Decimal("100.00"), False, False),
        (2, "Checking", "0", "USD", Decimal("50.00"), False, False),
    ])
    model.sort(0, Qt.AscendingOrder)
    assert _data(model, 0, 0) == "Checking"
    assert _data(model, 1, 0) == "savings"


def test_account_model_sort_by_type_descending():
    model = AccountTableModel([
        (1, "Checking", "0", "USD", Decimal("100.00"), False, False),
        (2, "Card", "1", "USD", Decimal("50.00"), False, False),
    ])
    model.sort(1, Qt.DescendingOrder)
    assert _data(model, 0, 1) == "Credit"
    assert _data(model, 1, 1) == "Checking/Savings"


def test_account_model_sort_by_balance_uses_usd_converted_value():
    # Raw balance order is Checking(300) < Savings(2000), but converted to USD
    # (Savings at 0.10 -> 200) the order flips: Savings(200) < Checking(300).
    model = AccountTableModel([
        (1, "Checking", "0", "USD", Decimal("300.00"), False, False),
        (2, "Savings", "0", "SEK", Decimal("2000.00"), False, False),
    ])
    model.set_exchange_rates({"SEK": Decimal("0.10")})
    model.sort(3, Qt.AscendingOrder)
    assert _data(model, 0, 0) == "Savings"
    assert _data(model, 1, 0) == "Checking"


def test_account_model_sort_on_empty_accounts_does_not_crash():
    model = AccountTableModel([])
    model.sort(0, Qt.AscendingOrder)
    assert model.rowCount() == 0


def test_open_account_name_has_no_prefix():
    model = AccountTableModel([(1, "Checking", "0", "USD", Decimal("100.00"), False, False)])
    assert _data(model, 0, 0) == "Checking"


def test_closed_account_name_is_prefixed_with_closed():
    model = AccountTableModel([(1, "Old Card", "1", "USD", Decimal("0.00"), True, False)])
    assert _data(model, 0, 0) == "(CLOSED) Old Card"


def test_favorite_account_row_has_gray_background():
    model = AccountTableModel([(1, "Checking", "0", "USD", Decimal("100.00"), False, True)])
    color = model.data(model.index(0, 0), Qt.BackgroundRole)
    assert color is not None


def test_non_favorite_account_row_has_no_background_override():
    model = AccountTableModel([(1, "Checking", "0", "USD", Decimal("100.00"), False, False)])
    assert model.data(model.index(0, 0), Qt.BackgroundRole) is None


def test_favorite_account_row_keeps_default_foreground_color():
    model = AccountTableModel([(1, "Checking", "0", "USD", Decimal("100.00"), False, True)])
    assert model.data(model.index(0, 0), Qt.ForegroundRole) is None


def test_favorite_account_row_uses_light_theme_gray_background_in_light_mode(qapp):
    model = AccountTableModel([(1, "Checking", "0", "USD", Decimal("100.00"), False, True)])
    color = model.data(model.index(0, 0), Qt.BackgroundRole)
    assert color == models.FAVORITE_BACKGROUND_LIGHT


def test_favorite_account_row_uses_dark_theme_gray_background_in_dark_mode(qapp):
    theme.apply_theme(qapp, True)
    try:
        model = AccountTableModel([(1, "Checking", "0", "USD", Decimal("100.00"), False, True)])
        color = model.data(model.index(0, 0), Qt.BackgroundRole)
        assert color == models.FAVORITE_BACKGROUND_DARK
    finally:
        theme.apply_theme(qapp, False)


def test_activity_buy_and_sell_are_translated_to_labels():
    assert activity_label("1") == "Buy"
    assert activity_label("2") == "Sell"


def test_rsu_activity_codes_are_translated_to_labels():
    assert activity_label("17") == "Grant"
    assert activity_label("18") == "Vested"
    assert activity_label("19") == "Sold"
    assert activity_label("20") == "Expired"


def test_unknown_activity_falls_back_to_raw_value():
    assert activity_label("99") == "Activity 99"


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
    assert _data(model, 0, 2) == "Grant"
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


LOAN_PRINCIPAL_ROW = (
    2000, date(2024, 1, 15), "NFCU", None, "Principal", Decimal("200.00"),
    None, None, None, None, "Principal",
)

LOAN_INTEREST_ROW = (
    None, date(2024, 1, 15), "NFCU", None, None, Decimal("30.00"),
    None, None, None, None, "Interest",
)


def test_loan_account_shows_loan_columns():
    model = TransactionTableModel()
    model.set_transactions([LOAN_PRINCIPAL_ROW, LOAN_INTEREST_ROW], is_loan=True)
    assert [
        model.headerData(i, Qt.Horizontal) for i in range(model.columnCount())
    ] == ["Date", "Payee", "Type", "Memo", "Amount"]
    assert _data(model, 0, 0) == "2024-01-15"
    assert _data(model, 0, 1) == "NFCU"
    assert _data(model, 0, 2) == "Principal"
    assert _data(model, 0, 3) == "Principal"
    assert _data(model, 0, 4) == "200.00"
    assert _data(model, 1, 2) == "Interest"
    assert _data(model, 1, 3) == ""


def test_switching_back_from_loan_restores_default_columns():
    model = TransactionTableModel()
    model.set_transactions([LOAN_PRINCIPAL_ROW], is_loan=True)
    model.set_transactions([NON_INVESTMENT_ROW], is_loan=False)
    assert model.columnCount() == 5
    assert _data(model, 0, 1) == "Store A"


def test_loan_transaction_at_returns_full_row_including_none_transaction_id():
    model = TransactionTableModel()
    model.set_transactions([LOAN_INTEREST_ROW], is_loan=True)
    assert model.transaction_at(0)[0] is None


def test_sort_loan_transactions_by_type():
    model = TransactionTableModel()
    model.set_transactions([LOAN_PRINCIPAL_ROW, LOAN_INTEREST_ROW], is_loan=True)
    model.sort(2, Qt.AscendingOrder)
    assert [_data(model, r, 2) for r in range(2)] == ["Interest", "Principal"]


def test_build_loan_transaction_rows_merges_principal_and_interest_sorted_by_date_desc():
    transactions = [
        (2000, date(2024, 1, 15), "NFCU", None, "Principal", Decimal("200.00"), None, None, None, None),
        (2001, date(2024, 2, 15), "NFCU", None, "Principal", Decimal("202.00"), None, None, None, None),
    ]
    interest_payments = [
        (date(2024, 2, 15), "NFCU", Decimal("28.00"), "USD"),
        (date(2024, 1, 15), "NFCU", Decimal("30.00"), "USD"),
    ]
    rows = build_loan_transaction_rows(transactions, interest_payments)
    assert [(row[1], row[10]) for row in rows] == [
        (date(2024, 2, 15), "Principal"),
        (date(2024, 2, 15), "Interest"),
        (date(2024, 1, 15), "Principal"),
        (date(2024, 1, 15), "Interest"),
    ]


def test_build_loan_transaction_rows_interest_rows_have_no_transaction_id():
    rows = build_loan_transaction_rows([], [(date(2024, 1, 15), "NFCU", Decimal("30.00"), "USD")])
    assert rows[0][0] is None
    assert rows[0][10] == "Interest"
    assert rows[0][5] == Decimal("30.00")
    assert rows[0][2] == "NFCU"


def test_build_loan_transaction_rows_preserves_principal_row_fields():
    transactions = [
        (2000, date(2024, 1, 15), "NFCU", None, "Principal", Decimal("200.00"), None, None, None, None),
    ]
    rows = build_loan_transaction_rows(transactions, [])
    assert rows[0] == (
        2000, date(2024, 1, 15), "NFCU", None, "Principal", Decimal("200.00"),
        None, None, None, None, "Principal",
    )


def _identity_to_usd(_currency, amount):
    return amount


def test_compute_loan_totals_sums_principal_and_interest_separately():
    transactions = [
        (2000, date(2024, 1, 15), "NFCU", None, "Principal", Decimal("200.00"), None, None, None, None),
        (2001, date(2024, 2, 15), "NFCU", None, "Principal", Decimal("202.00"), None, None, None, None),
    ]
    interest_payments = [
        (date(2024, 1, 15), "NFCU", Decimal("30.00"), "USD"),
        (date(2024, 2, 15), "NFCU", Decimal("28.00"), "USD"),
    ]
    assert compute_loan_totals(transactions, interest_payments, _identity_to_usd) == (
        Decimal("402.00"), Decimal("58.00"),
    )


def test_compute_loan_totals_converts_each_interest_payment_by_its_own_currency():
    # Interest legs come from the paying account, which may be denominated
    # differently than the loan itself — each must be converted using its
    # own currency, not the loan's.
    interest_payments = [
        (date(2024, 1, 15), "NFCU", Decimal("100.00"), "SEK"),
        (date(2024, 2, 15), "NFCU", Decimal("28.00"), "USD"),
    ]
    to_usd = lambda currency, amount: amount / 10 if currency == "SEK" else amount
    assert compute_loan_totals([], interest_payments, to_usd) == (
        Decimal("0"), Decimal("38.00"),
    )


def test_compute_loan_totals_empty_returns_zero():
    assert compute_loan_totals([], [], _identity_to_usd) == (Decimal("0"), Decimal("0"))


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


def test_compute_account_value_history_counts_vested_rsu_shares():
    rows = [
        (1, date(2024, 1, 20), None, None, None, Decimal("0.00"),
         "RSU Grant A", "17", Decimal("10.0"), Decimal("0.00")),
        (2, date(2024, 2, 20), None, None, None, Decimal("0.00"),
         "RSU Grant A", "18", Decimal("6.0"), None),
        (3, date(2024, 3, 20), None, None, None, Decimal("-80.00"),
         "RSU Grant A", "19", Decimal("2.0"), Decimal("40.00")),
    ]
    history = compute_account_value_history(rows, Decimal("0.00"), is_investment=True)
    assert history == [
        (date(2024, 2, 20), Decimal("0.00")),   # 6 vested, no known price yet
        (date(2024, 3, 20), Decimal("160.00")),  # 4 remaining * $40
    ]


def test_compute_account_value_history_excludes_rsu_vests_after_today():
    rows = [
        (1, date(2024, 2, 20), None, None, None, Decimal("0.00"),
         "RSU Grant A", "18", Decimal("6.0"), None),
        (2, date(2024, 3, 20), None, None, None, Decimal("-80.00"),
         "RSU Grant A", "19", Decimal("2.0"), Decimal("40.00")),
        (3, date(2099, 1, 1), None, None, None, Decimal("0.00"),
         "RSU Grant A", "18", Decimal("4.0"), None),
    ]
    history = compute_account_value_history(
        rows, Decimal("0.00"), is_investment=True, today=date(2024, 6, 1)
    )
    assert history == [
        (date(2024, 2, 20), Decimal("0.00")),
        (date(2024, 3, 20), Decimal("160.00")),
    ]


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
        ("USD", Decimal("100"), [(date(2024, 1, 15), Decimal("150"))], None, False),
        ("SEK", Decimal("0"), [(date(2024, 1, 10), Decimal("1000"))], None, False),
    ]

    def to_usd(currency, amount):
        return amount if currency == "USD" else amount * Decimal("0.1")

    series = compute_net_worth_series(accounts, [date(2024, 1, 1)], to_usd)
    assert series == [(date(2024, 1, 1), Decimal("100"))]


def test_compute_net_worth_series_sums_accounts_converted_to_usd_as_of_each_date():
    accounts = [
        ("USD", Decimal("100"), [(date(2024, 1, 15), Decimal("150"))], None, False),
        ("SEK", Decimal("0"), [(date(2024, 1, 10), Decimal("1000"))], None, False),
    ]

    def to_usd(currency, amount):
        return amount if currency == "USD" else amount * Decimal("0.1")

    series = compute_net_worth_series(accounts, [date(2024, 1, 1), date(2024, 2, 1)], to_usd)
    assert series == [
        (date(2024, 1, 1), Decimal("100")),
        (date(2024, 2, 1), Decimal("250")),
    ]


def test_compute_net_worth_series_holds_last_value_flat_after_final_transaction():
    accounts = [("USD", Decimal("0"), [(date(2024, 1, 10), Decimal("500"))], None, False)]
    series = compute_net_worth_series(
        accounts, [date(2024, 6, 1)], to_usd=lambda currency, amount: amount
    )
    assert series == [(date(2024, 6, 1), Decimal("500"))]


def test_compute_net_worth_series_excludes_account_before_its_date_opened():
    # opening_balance (-400000) shouldn't count for sample dates before the
    # account was actually opened, even though it's the "initial_value"
    # used once the account's history begins.
    accounts = [
        ("USD", Decimal("-400000"), [(date(2002, 1, 11), Decimal("-399000"))], date(2001, 10, 15), False),
    ]
    series = compute_net_worth_series(
        accounts, [date(2001, 1, 1)], to_usd=lambda currency, amount: amount
    )
    assert series == [(date(2001, 1, 1), Decimal("0"))]


def test_compute_net_worth_series_uses_first_transaction_when_earlier_than_date_opened():
    # Money's recorded open date can itself postdate the first real
    # transaction; the earlier of the two should win.
    accounts = [
        ("USD", Decimal("-1000"), [(date(2008, 3, 22), Decimal("-800"))], date(2008, 4, 1), False),
    ]
    series = compute_net_worth_series(
        accounts, [date(2008, 3, 22)], to_usd=lambda currency, amount: amount
    )
    assert series == [(date(2008, 3, 22), Decimal("-800"))]


def test_compute_net_worth_series_excludes_closed_account_after_its_last_transaction():
    # A closed loan whose recorded history stops without reaching zero
    # (e.g. paid off via refinance with no reconciling transaction)
    # shouldn't keep dragging down net worth after it closed.
    accounts = [
        ("USD", Decimal("0"), [(date(2010, 1, 1), Decimal("-339204.15"))], None, True),
    ]
    series = compute_net_worth_series(
        accounts, [date(2020, 1, 1)], to_usd=lambda currency, amount: amount
    )
    assert series == [(date(2020, 1, 1), Decimal("0"))]


def test_compute_net_worth_series_still_holds_open_accounts_flat_after_last_transaction():
    # is_closed=False accounts should keep the old carry-forward behavior.
    accounts = [
        ("USD", Decimal("0"), [(date(2010, 1, 1), Decimal("500"))], None, False),
    ]
    series = compute_net_worth_series(
        accounts, [date(2020, 1, 1)], to_usd=lambda currency, amount: amount
    )
    assert series == [(date(2020, 1, 1), Decimal("500"))]


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


def test_compute_income_by_category_sorts_highest_income_first():
    transactions = [
        (10, "Salary", date(2024, 3, 1), Decimal("1200.00"), "USD"),
        (20, "Freelance", date(2024, 3, 10), Decimal("300.00"), "USD"),
        (20, "Freelance", date(2024, 3, 15), Decimal("200.00"), "USD"),
    ]
    result = compute_income_by_category(
        transactions, date(2024, 1, 1), date(2024, 12, 31), to_usd=lambda currency, amount: amount
    )
    assert result == [
        ("Salary", Decimal("1200.00")),
        ("Freelance", Decimal("500.00")),
    ]


def test_compute_income_by_category_ignores_negative_amounts():
    transactions = [
        (10, "Salary", date(2024, 3, 1), Decimal("1200.00"), "USD"),
        (20, "Groceries", date(2024, 3, 5), Decimal("-30.00"), "USD"),
    ]
    result = compute_income_by_category(
        transactions, date(2024, 1, 1), date(2024, 12, 31), to_usd=lambda currency, amount: amount
    )
    assert result == [("Salary", Decimal("1200.00"))]


def test_compute_investment_analysis_sorts_by_highest_percentage_increase_first():
    prices = [
        ("Fund A", date(2024, 1, 1), Decimal("10.00")),
        ("Fund A", date(2024, 2, 1), Decimal("20.00")),
        ("Fund B", date(2024, 1, 1), Decimal("50.00")),
        ("Fund B", date(2024, 2, 1), Decimal("55.00")),
    ]
    result = compute_investment_analysis(prices, date(2024, 1, 1), date(2024, 12, 31))
    assert result == [
        ("Fund A", Decimal("100"), Decimal("10.00"), Decimal("20.00"), date(2024, 1, 1), date(2024, 2, 1)),
        ("Fund B", Decimal("10"), Decimal("50.00"), Decimal("55.00"), date(2024, 1, 1), date(2024, 2, 1)),
    ]


def test_compute_investment_analysis_filters_to_date_range():
    prices = [
        ("Fund A", date(2024, 1, 1), Decimal("10.00")),
        ("Fund A", date(2024, 2, 1), Decimal("20.00")),
        ("Fund A", date(2024, 6, 1), Decimal("5.00")),
    ]
    result = compute_investment_analysis(prices, date(2024, 1, 1), date(2024, 3, 1))
    assert result == [
        ("Fund A", Decimal("100"), Decimal("10.00"), Decimal("20.00"), date(2024, 1, 1), date(2024, 2, 1)),
    ]


def test_compute_investment_analysis_excludes_investments_with_no_prices_in_range():
    prices = [
        ("Fund A", date(2024, 1, 1), Decimal("10.00")),
        ("Fund B", date(2024, 6, 1), Decimal("5.00")),
    ]
    result = compute_investment_analysis(prices, date(2024, 1, 1), date(2024, 3, 1))
    assert [row[0] for row in result] == ["Fund A"]


def test_compute_investment_analysis_single_price_point_has_zero_percent_increase():
    prices = [("Fund A", date(2024, 1, 1), Decimal("10.00"))]
    result = compute_investment_analysis(prices, date(2024, 1, 1), date(2024, 12, 31))
    assert result == [
        ("Fund A", Decimal("0"), Decimal("10.00"), Decimal("10.00"), date(2024, 1, 1), date(2024, 1, 1)),
    ]


def test_compute_investment_analysis_zero_lowest_price_does_not_crash():
    prices = [
        ("Fund A", date(2024, 1, 1), Decimal("0.00")),
        ("Fund A", date(2024, 2, 1), Decimal("5.00")),
    ]
    result = compute_investment_analysis(prices, date(2024, 1, 1), date(2024, 12, 31))
    assert result == [
        ("Fund A", Decimal("0"), Decimal("0.00"), Decimal("5.00"), date(2024, 1, 1), date(2024, 2, 1)),
    ]


def test_compute_investment_analysis_empty_prices_returns_empty_list():
    assert compute_investment_analysis([], date(2024, 1, 1), date(2024, 12, 31)) == []


def test_investment_analysis_model_columns_are_name_percent_prices_and_range():
    model = InvestmentAnalysisTableModel(
        [("Fund A", Decimal("100"), Decimal("10.00"), Decimal("20.00"), date(2024, 1, 1), date(2024, 2, 1))]
    )
    assert model.rowCount() == 1
    assert model.columnCount() == 5
    assert _data(model, 0, 0) == "Fund A"
    assert _data(model, 0, 1) == "+100.00%"
    assert _data(model, 0, 2) == "10.00"
    assert _data(model, 0, 3) == "20.00"
    assert _data(model, 0, 4) == "2024-01-01 to 2024-02-01"


def test_investment_analysis_model_set_investments_replaces_contents():
    model = InvestmentAnalysisTableModel()
    assert model.rowCount() == 0
    model.set_investments(
        [("Fund A", Decimal("100"), Decimal("10.00"), Decimal("20.00"), date(2024, 1, 1), date(2024, 2, 1))]
    )
    assert model.rowCount() == 1
    assert _data(model, 0, 0) == "Fund A"


def test_investment_analysis_model_sort_ascending_by_percent_increase():
    model = InvestmentAnalysisTableModel(
        [
            ("Fund A", Decimal("100"), Decimal("10.00"), Decimal("20.00"), date(2024, 1, 1), date(2024, 2, 1)),
            ("Fund B", Decimal("10"), Decimal("50.00"), Decimal("55.00"), date(2024, 1, 1), date(2024, 2, 1)),
        ]
    )
    model.sort(1, Qt.AscendingOrder)
    assert _data(model, 0, 0) == "Fund B"
    assert _data(model, 1, 0) == "Fund A"


def test_investment_analysis_model_sort_descending_by_percent_increase():
    model = InvestmentAnalysisTableModel(
        [
            ("Fund B", Decimal("10"), Decimal("50.00"), Decimal("55.00"), date(2024, 1, 1), date(2024, 2, 1)),
            ("Fund A", Decimal("100"), Decimal("10.00"), Decimal("20.00"), date(2024, 1, 1), date(2024, 2, 1)),
        ]
    )
    model.sort(1, Qt.DescendingOrder)
    assert _data(model, 0, 0) == "Fund A"
    assert _data(model, 1, 0) == "Fund B"


def test_investment_analysis_model_sort_by_name_column():
    model = InvestmentAnalysisTableModel(
        [
            ("Fund B", Decimal("10"), Decimal("50.00"), Decimal("55.00"), date(2024, 1, 1), date(2024, 2, 1)),
            ("Fund A", Decimal("100"), Decimal("10.00"), Decimal("20.00"), date(2024, 1, 1), date(2024, 2, 1)),
        ]
    )
    model.sort(0, Qt.AscendingOrder)
    assert _data(model, 0, 0) == "Fund A"
    assert _data(model, 1, 0) == "Fund B"


def test_compute_income_by_category_filters_to_date_range():
    transactions = [
        (10, "Salary", date(2024, 1, 1), Decimal("1200.00"), "USD"),
        (20, "Freelance", date(2024, 6, 1), Decimal("300.00"), "USD"),
    ]
    result = compute_income_by_category(
        transactions, date(2024, 5, 1), date(2024, 12, 31), to_usd=lambda currency, amount: amount
    )
    assert result == [("Freelance", Decimal("300.00"))]


def test_compute_income_by_category_converts_currency():
    transactions = [(10, "Consulting", date(2024, 3, 1), Decimal("100.00"), "SEK")]
    result = compute_income_by_category(
        transactions,
        date(2024, 1, 1),
        date(2024, 12, 31),
        to_usd=lambda currency, amount: amount * Decimal("0.1"),
    )
    assert result == [("Consulting", Decimal("10.000"))]


def test_compute_income_by_category_empty_transactions_returns_empty_list():
    assert compute_income_by_category([], date(2024, 1, 1), date(2024, 12, 31), lambda c, a: a) == []


def test_income_by_category_model_columns_are_category_and_income():
    model = IncomeByCategoryTableModel([("Salary", Decimal("1200.00"))])
    assert model.rowCount() == 1
    assert model.columnCount() == 2
    assert _data(model, 0, 0) == "Salary"
    assert _data(model, 0, 1) == "1,200.00"
