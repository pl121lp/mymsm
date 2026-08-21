from datetime import date
from decimal import Decimal

import pytest

import data
from writes import add_account, add_transaction, set_account_closed, update_transaction


def test_add_account_inserts_row_with_max_id_plus_one(conn):
    # conn fixture seeds account_ids up to 3 (see conftest.py).
    account_id = add_account(
        conn, name="New Savings", account_type="0", currency="USD",
        opening_balance=Decimal("250.00"),
    )
    assert account_id == 4
    row = conn.execute(
        "SELECT account_id, name, account_type, is_closed, opening_balance, currency "
        "FROM accounts WHERE account_id = ?",
        [account_id],
    ).fetchone()
    assert row == (4, "New Savings", "0", False, Decimal("250.00"), "USD")


def test_set_account_closed_closes_open_account(conn):
    set_account_closed(conn, account_id=1, is_closed=True)
    row = conn.execute("SELECT is_closed FROM accounts WHERE account_id = 1").fetchone()
    assert row == (True,)


def test_set_account_closed_reopens_closed_account(conn):
    # account_id 2 ("Old Card") is seeded as closed (see conftest.py).
    set_account_closed(conn, account_id=2, is_closed=False)
    row = conn.execute("SELECT is_closed FROM accounts WHERE account_id = 2").fetchone()
    assert row == (False,)


def test_add_transaction_inserts_plain_cash_row(conn):
    transaction_id = add_transaction(
        conn, account_id=1, txn_date=date(2024, 4, 1), amount=Decimal("-10.00"), memo="coffee",
    )
    row = conn.execute(
        "SELECT transaction_id, account_id, txn_date, amount, memo FROM transactions "
        "WHERE transaction_id = ?",
        [transaction_id],
    ).fetchone()
    assert row == (transaction_id, 1, date(2024, 4, 1), Decimal("-10.00"), "coffee")


def test_add_transaction_uses_max_id_plus_one(conn):
    # conn fixture seeds transaction_ids up to 3003 (see conftest.py).
    transaction_id = add_transaction(
        conn, account_id=1, txn_date=date(2024, 4, 1), amount=Decimal("5.00"),
    )
    assert transaction_id == 3004


def test_add_transaction_creates_new_payee_and_category(conn):
    transaction_id = add_transaction(
        conn, account_id=1, txn_date=date(2024, 4, 1), amount=Decimal("-9.00"),
        payee_name="New Cafe", category_name="Dining",
    )
    assert "New Cafe" in [name for _id, name in data.list_payees(conn)]
    assert "Dining" in [name for _id, name in data.list_categories(conn)]
    row = conn.execute(
        "SELECT p.name, c.name FROM transactions t "
        "JOIN payees p ON p.payee_id = t.payee_id "
        "JOIN categories c ON c.category_id = t.category_id "
        "WHERE t.transaction_id = ?",
        [transaction_id],
    ).fetchone()
    assert row == ("New Cafe", "Dining")


def test_add_transaction_reuses_existing_payee_case_insensitive(conn):
    before = len(data.list_payees(conn))
    add_transaction(
        conn, account_id=1, txn_date=date(2024, 4, 1), amount=Decimal("-1.00"),
        payee_name="store a",  # seeded payee is "Store A" (payee_id 100)
    )
    assert len(data.list_payees(conn)) == before
    row = conn.execute(
        "SELECT payee_id FROM transactions ORDER BY transaction_id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == 100


def test_add_transaction_creates_new_security_for_investment(conn):
    transaction_id = add_transaction(
        conn, account_id=3, txn_date=date(2024, 4, 1), amount=Decimal("100.00"),
        security_name="New Fund", activity="1", quantity=Decimal("5.0"), price=Decimal("20.00"),
    )
    assert "New Fund" in [name for _id, name in data.list_securities(conn)]
    row = conn.execute(
        "SELECT sec.name, t.activity, t.quantity, t.price FROM transactions t "
        "JOIN securities sec ON sec.security_id = t.security_id "
        "WHERE t.transaction_id = ?",
        [transaction_id],
    ).fetchone()
    assert row == ("New Fund", "1", Decimal("5.0"), Decimal("20.00"))


def test_add_transaction_rolls_back_dictionary_inserts_on_failure(conn):
    before_payees = data.list_payees(conn)
    with pytest.raises(Exception):
        add_transaction(
            conn, account_id=1, txn_date=None, amount=Decimal("-1.00"),
            payee_name="Orphan Payee",
        )
    assert data.list_payees(conn) == before_payees


def test_update_transaction_changes_plain_cash_row(conn):
    result_id = update_transaction(
        conn, transaction_id=1000, txn_date=date(2024, 4, 2), amount=Decimal("-30.00"),
        memo="corrected",
    )
    assert result_id == 1000
    row = conn.execute(
        "SELECT transaction_id, txn_date, amount, memo FROM transactions "
        "WHERE transaction_id = 1000"
    ).fetchone()
    assert row == (1000, date(2024, 4, 2), Decimal("-30.00"), "corrected")


def test_update_transaction_creates_new_payee_and_category(conn):
    update_transaction(
        conn, transaction_id=1000, txn_date=date(2024, 3, 15), amount=Decimal("-52.30"),
        payee_name="New Cafe", category_name="Dining",
    )
    assert "New Cafe" in [name for _id, name in data.list_payees(conn)]
    assert "Dining" in [name for _id, name in data.list_categories(conn)]
    row = conn.execute(
        "SELECT p.name, c.name FROM transactions t "
        "JOIN payees p ON p.payee_id = t.payee_id "
        "JOIN categories c ON c.category_id = t.category_id "
        "WHERE t.transaction_id = 1000"
    ).fetchone()
    assert row == ("New Cafe", "Dining")


def test_update_transaction_reuses_existing_payee_case_insensitive(conn):
    before = len(data.list_payees(conn))
    update_transaction(
        conn, transaction_id=1001, txn_date=date(2024, 3, 10), amount=Decimal("1000.00"),
        payee_name="store a",  # seeded payee is "Store A" (payee_id 100)
    )
    assert len(data.list_payees(conn)) == before
    row = conn.execute(
        "SELECT payee_id FROM transactions WHERE transaction_id = 1001"
    ).fetchone()
    assert row[0] == 100


def test_update_transaction_creates_new_security_for_investment(conn):
    update_transaction(
        conn, transaction_id=3000, txn_date=date(2024, 1, 10), amount=Decimal("100.00"),
        security_name="New Fund", activity="1", quantity=Decimal("5.0"), price=Decimal("20.00"),
    )
    assert "New Fund" in [name for _id, name in data.list_securities(conn)]
    row = conn.execute(
        "SELECT sec.name, t.activity, t.quantity, t.price FROM transactions t "
        "JOIN securities sec ON sec.security_id = t.security_id "
        "WHERE t.transaction_id = 3000"
    ).fetchone()
    assert row == ("New Fund", "1", Decimal("5.0"), Decimal("20.00"))


def test_update_transaction_rolls_back_dictionary_inserts_on_failure(conn):
    before_payees = data.list_payees(conn)
    with pytest.raises(Exception):
        update_transaction(
            conn, transaction_id=1000, txn_date=None, amount=Decimal("-1.00"),
            payee_name="Orphan Payee",
        )
    assert data.list_payees(conn) == before_payees
