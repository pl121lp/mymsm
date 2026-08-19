from datetime import date
from decimal import Decimal

from data import list_accounts, list_transactions


def test_list_accounts_excludes_closed_by_default(conn):
    assert list_accounts(conn) == [(1, "Checking", "Bank")]


def test_list_accounts_includes_closed_when_requested(conn):
    assert list_accounts(conn, include_closed=True) == [
        (1, "Checking", "Bank"),
        (2, "Old Card", "Credit"),
    ]


def test_list_transactions_returns_joined_rows_sorted_by_date_desc(conn):
    transactions = list_transactions(conn, account_id=1)
    assert transactions == [
        (1000, date(2024, 3, 15), "Store A", "Groceries", "weekly shop", Decimal("-52.30")),
        (1001, date(2024, 3, 10), None, None, None, Decimal("1000.00")),
    ]


def test_list_transactions_unknown_account_returns_empty(conn):
    assert list_transactions(conn, account_id=999) == []
