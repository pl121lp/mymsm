from datetime import date
from decimal import Decimal

from data import (
    count_transactions_by_payee,
    list_accounts,
    list_categories,
    list_category_transactions,
    list_payee_transactions,
    list_securities,
    list_security_history,
    list_transactions,
    search_transactions,
)


def test_list_accounts_excludes_closed_by_default(conn):
    assert list_accounts(conn) == [
        (3, "Brokerage", "5", "SEK", Decimal("226.30"), False),
        (1, "Checking", "Bank", "USD", Decimal("1047.70"), False),
    ]


def test_list_accounts_includes_closed_when_requested(conn):
    assert list_accounts(conn, include_closed=True) == [
        (3, "Brokerage", "5", "SEK", Decimal("226.30"), False),
        (1, "Checking", "Bank", "USD", Decimal("1047.70"), False),
        (2, "Old Card", "Credit", "USD", Decimal("0.00"), True),
    ]


def test_list_accounts_orders_by_account_type_then_name(conn):
    conn.execute(
        "INSERT INTO accounts VALUES "
        "(4, 'Roth IRA', '5', FALSE, 0.00, 'USD'), "
        "(5, 'House', '3', FALSE, 500000.00, 'USD'), "
        "(6, 'Mortgage', '6', FALSE, -300000.00, 'USD'), "
        "(7, 'Visa', '1', FALSE, 0.00, 'USD'), "
        "(8, 'Savings', '0', FALSE, 50.00, 'USD')"
    )
    names_in_order = [row[1] for row in list_accounts(conn)]
    assert names_in_order == [
        "Savings",     # checking/savings ("0")
        "Visa",        # credit ("1")
        "Brokerage",   # investment ("5")
        "Roth IRA",    # investment ("5")
        "Mortgage",    # loan ("6")
        "House",       # asset ("3")
        "Checking",    # unrecognized type ("Bank"), alphabetical fallback
    ]


def test_list_transactions_returns_joined_rows_sorted_by_date_desc(conn):
    transactions = list_transactions(conn, account_id=1)
    assert transactions == [
        (
            1000, date(2024, 3, 15), "Store A", "Groceries", "weekly shop", Decimal("-52.30"),
            None, None, None, None,
        ),
        (
            1001, date(2024, 3, 10), None, None, None, Decimal("1000.00"),
            None, None, None, None,
        ),
    ]


def test_list_transactions_resolves_investment_fields(conn):
    transactions = list_transactions(conn, account_id=3)
    buy = next(t for t in transactions if t[0] == 3000)
    assert buy == (
        3000, date(2024, 1, 10), None, None, None, Decimal("147.12"),
        "Vanguard Total Stock Market Index", "1", Decimal("8.0"), Decimal("18.39"),
    )


def test_list_transactions_unknown_account_returns_empty(conn):
    assert list_transactions(conn, account_id=999) == []


def test_list_categories_returns_all_ordered_by_name(dict_conn):
    assert list_categories(dict_conn) == [
        (20, "Groceries"),
        (10, "Utilities"),
    ]


def test_list_category_transactions_returns_rows_across_accounts_sorted_by_date_desc(dict_conn):
    assert list_category_transactions(dict_conn, category_id=20) == [
        (1000, date(2024, 3, 15), "Checking", "Store A", "weekly shop", Decimal("-52.30")),
        (1001, date(2024, 3, 10), "Savings", "Store B", "snacks", Decimal("-20.00")),
    ]


def test_list_category_transactions_unknown_category_returns_empty(dict_conn):
    assert list_category_transactions(dict_conn, category_id=999) == []


def test_list_securities_returns_all_ordered_by_name(dict_conn):
    assert list_securities(dict_conn) == [
        (501, "Apple Inc"),
        (500, "Vanguard Total Stock Market Index"),
    ]


def test_list_security_history_computes_per_account_running_total(dict_conn):
    assert list_security_history(dict_conn, security_id=500) == [
        (3, "Brokerage A", date(2024, 1, 10), Decimal("18.39"), Decimal("8.0")),
        (3, "Brokerage A", date(2024, 2, 10), Decimal("21.54"), Decimal("11.0")),
        (3, "Brokerage A", date(2024, 3, 1), Decimal("22.63"), Decimal("10.0")),
        (4, "Brokerage B", date(2024, 1, 15), Decimal("20.00"), Decimal("10.0")),
        (4, "Brokerage B", date(2024, 2, 20), Decimal("25.00"), Decimal("8.0")),
    ]


def test_list_security_history_unknown_security_returns_empty(dict_conn):
    assert list_security_history(dict_conn, security_id=999) == []


def test_count_transactions_by_payee_ignores_null_payee(dict_conn):
    assert count_transactions_by_payee(dict_conn) == {100: 1, 101: 1}


def test_list_payee_transactions_accepts_multiple_ids(dict_conn):
    assert list_payee_transactions(dict_conn, [100, 101]) == [
        (1000, date(2024, 3, 15), "Checking", "Groceries", "weekly shop", Decimal("-52.30")),
        (1001, date(2024, 3, 10), "Savings", "Groceries", "snacks", Decimal("-20.00")),
    ]


def test_list_payee_transactions_empty_ids_returns_empty(dict_conn):
    assert list_payee_transactions(dict_conn, []) == []


def test_search_transactions_no_filters_returns_all_sorted_by_date_desc(dict_conn):
    transaction_ids = [row[0] for row in search_transactions(dict_conn)]
    assert transaction_ids == [1000, 1001, 3002, 1002, 4001, 3001, 4000, 3000]


def test_search_transactions_returns_full_row_shape_for_editing(dict_conn):
    rows = search_transactions(dict_conn, payee="Store A")
    assert rows == [
        (
            1000, date(2024, 3, 15), 1, "Checking", "Bank",
            "Store A", "Groceries", "weekly shop", Decimal("-52.30"),
            None, None, None, None,
        ),
    ]


def test_search_transactions_filters_by_payee_substring_case_insensitive(dict_conn):
    transaction_ids = {row[0] for row in search_transactions(dict_conn, payee="store b")}
    assert transaction_ids == {1001}


def test_search_transactions_filters_by_category_substring(dict_conn):
    transaction_ids = {row[0] for row in search_transactions(dict_conn, category="util")}
    assert transaction_ids == {1002}


def test_search_transactions_filters_by_investment_substring(dict_conn):
    transaction_ids = {row[0] for row in search_transactions(dict_conn, investment="apple")}
    assert transaction_ids == set()
    transaction_ids = {row[0] for row in search_transactions(dict_conn, investment="vanguard")}
    assert transaction_ids == {3000, 3001, 3002, 4000, 4001}


def test_search_transactions_filters_by_memo_substring(dict_conn):
    transaction_ids = {row[0] for row in search_transactions(dict_conn, memo="bill")}
    assert transaction_ids == {1002}


def test_search_transactions_filters_by_amount_range(dict_conn):
    transaction_ids = {
        row[0] for row in search_transactions(dict_conn, amount_min=Decimal("0"), amount_max=Decimal("100"))
    }
    assert transaction_ids == {3001}


def test_search_transactions_filters_by_amount_min_only(dict_conn):
    transaction_ids = {row[0] for row in search_transactions(dict_conn, amount_min=Decimal("100"))}
    assert transaction_ids == {3000, 4000}


def test_search_transactions_filters_by_amount_max_only(dict_conn):
    transaction_ids = {row[0] for row in search_transactions(dict_conn, amount_max=Decimal("-50"))}
    assert transaction_ids == {1000, 1002, 4001}


def test_search_transactions_filters_by_date_min(dict_conn):
    transaction_ids = {row[0] for row in search_transactions(dict_conn, date_min=date(2024, 3, 1))}
    assert transaction_ids == {1000, 1001, 1002, 3002}


def test_search_transactions_filters_by_date_max(dict_conn):
    transaction_ids = {row[0] for row in search_transactions(dict_conn, date_max=date(2024, 1, 15))}
    assert transaction_ids == {3000, 4000}


def test_search_transactions_filters_by_date_range(dict_conn):
    transaction_ids = {
        row[0]
        for row in search_transactions(dict_conn, date_min=date(2024, 2, 1), date_max=date(2024, 2, 28))
    }
    assert transaction_ids == {3001, 4001}


def test_search_transactions_filters_by_account_ids(dict_conn):
    transaction_ids = {row[0] for row in search_transactions(dict_conn, account_ids=[3])}
    assert transaction_ids == {3000, 3001, 3002}


def test_search_transactions_combines_filters_with_and(dict_conn):
    transaction_ids = {
        row[0] for row in search_transactions(dict_conn, category="Groceries", amount_max=Decimal("-30"))
    }
    assert transaction_ids == {1000}
