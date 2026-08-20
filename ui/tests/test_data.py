from datetime import date
from decimal import Decimal

from data import list_accounts, list_categories, list_category_transactions, list_transactions


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
