from datetime import date
from decimal import Decimal

import pytest

import data
from qfx_import import QfxRecord
from writes import (
    add_account,
    add_transaction,
    delete_account,
    delete_transaction,
    delete_transactions,
    import_transactions,
    restore_transaction,
    restore_transaction_fields,
    set_account_closed,
    update_account,
    update_transaction,
)


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


def test_update_account_changes_name_and_opening_balance(conn):
    update_account(conn, account_id=1, name="Checking Renamed", opening_balance=Decimal("200.00"))
    row = conn.execute(
        "SELECT name, opening_balance FROM accounts WHERE account_id = 1"
    ).fetchone()
    assert row == ("Checking Renamed", Decimal("200.00"))


def test_update_account_leaves_other_fields_intact(conn):
    update_account(conn, account_id=1, name="Checking Renamed", opening_balance=Decimal("200.00"))
    row = conn.execute(
        "SELECT account_type, currency, is_closed FROM accounts WHERE account_id = 1"
    ).fetchone()
    assert row == ("Bank", "USD", False)


def test_delete_transaction_removes_the_transaction_row(conn):
    # transaction_id 1000 belongs to account 1 (see conftest.py).
    delete_transaction(conn, transaction_id=1000)
    row = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    assert row is None


def test_delete_transaction_leaves_other_transactions_intact(conn):
    delete_transaction(conn, transaction_id=1000)
    row = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id = 1001"
    ).fetchone()
    assert row == (1001,)


def test_restore_transaction_reinserts_deleted_row_with_same_id(conn):
    row = conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    delete_transaction(conn, transaction_id=1000)

    restore_transaction(conn, row)

    restored = conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    assert restored == row


def test_restore_transaction_leaves_other_rows_intact(conn):
    row = conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    delete_transaction(conn, transaction_id=1000)

    restore_transaction(conn, row)

    other = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id = 1001"
    ).fetchone()
    assert other == (1001,)


def test_restore_transaction_fields_reverts_an_edit(conn):
    before = conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    update_transaction(
        conn, transaction_id=1000, txn_date=date(2024, 4, 2), amount=Decimal("-99.00"),
        memo="edited",
    )

    restore_transaction_fields(conn, before)

    after = conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    assert after == before


def test_restore_transaction_fields_does_not_touch_account_id_or_transaction_id(conn):
    before = conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = 1000"
    ).fetchone()

    restore_transaction_fields(conn, before)  # no prior edit — should be a no-op

    after = conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    assert after == before


def test_delete_account_removes_the_account_row(conn):
    # account_id 2 ("Old Card") has no transactions (see conftest.py).
    delete_account(conn, account_id=2)
    row = conn.execute("SELECT account_id FROM accounts WHERE account_id = 2").fetchone()
    assert row is None


def test_delete_account_removes_its_transactions(conn):
    # account_id 1 ("Checking") has transactions 1000 and 1001 (see conftest.py).
    delete_account(conn, account_id=1)
    rows = conn.execute("SELECT transaction_id FROM transactions WHERE account_id = 1").fetchall()
    assert rows == []


def test_delete_account_leaves_other_accounts_transactions_intact(conn):
    delete_account(conn, account_id=1)
    row = conn.execute("SELECT transaction_id FROM transactions WHERE transaction_id = 1000").fetchone()
    assert row is None
    other_rows = conn.execute("SELECT transaction_id FROM transactions WHERE account_id = 3").fetchall()
    assert len(other_rows) == 4


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


def test_delete_transactions_removes_all_given_ids(conn):
    delete_transactions(conn, [1000, 1001])
    rows = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id IN (1000, 1001)"
    ).fetchall()
    assert rows == []


def test_delete_transactions_leaves_other_rows_intact(conn):
    delete_transactions(conn, [1000])
    row = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id = 1001"
    ).fetchone()
    assert row == (1001,)


def test_delete_transactions_does_nothing_for_empty_list(conn):
    before_count = len(data.list_transactions(conn, account_id=1))
    delete_transactions(conn, [])
    assert len(data.list_transactions(conn, account_id=1)) == before_count


def _qfx_record(name="New Payee", memo="a memo", amount="-10.00", txn_date=date(2024, 4, 1)):
    return QfxRecord(
        trn_type="DEBIT", txn_date=txn_date, amount=Decimal(amount),
        fitid="1", name=name, memo=memo, checknum="",
    )


def test_import_transactions_inserts_one_row_per_record(conn):
    records = [
        _qfx_record(name="Store A", amount="-5.00", txn_date=date(2024, 4, 1)),
        _qfx_record(name="New Cafe", amount="-9.00", txn_date=date(2024, 4, 2)),
    ]

    transaction_ids = import_transactions(conn, account_id=1, records=records)

    assert len(transaction_ids) == 2
    rows = conn.execute(
        "SELECT t.txn_date, t.amount, t.memo, p.name FROM transactions t "
        "JOIN payees p ON p.payee_id = t.payee_id "
        "WHERE t.account_id = 1 AND t.txn_date IN ('2024-04-01', '2024-04-02') "
        "ORDER BY t.txn_date"
    ).fetchall()
    assert rows == [
        (date(2024, 4, 1), Decimal("-5.00"), "a memo", "Store A"),
        (date(2024, 4, 2), Decimal("-9.00"), "a memo", "New Cafe"),
    ]


def test_import_transactions_reuses_existing_payee_case_insensitive(conn):
    before = len(data.list_payees(conn))
    import_transactions(conn, account_id=1, records=[_qfx_record(name="store a")])
    assert len(data.list_payees(conn)) == before
    row = conn.execute(
        "SELECT payee_id FROM transactions ORDER BY transaction_id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == 100


def test_import_transactions_creates_new_payee_for_unknown_name(conn):
    import_transactions(conn, account_id=1, records=[_qfx_record(name="Brand New Payee")])
    assert "Brand New Payee" in [name for _id, name in data.list_payees(conn)]


def test_import_transactions_treats_blank_name_as_no_payee(conn):
    import_transactions(conn, account_id=1, records=[_qfx_record(name="")])
    row = conn.execute(
        "SELECT payee_id FROM transactions ORDER BY transaction_id DESC LIMIT 1"
    ).fetchone()
    assert row[0] is None


def test_import_transactions_uses_sequential_ids_after_max(conn):
    # conn fixture seeds transaction_ids up to 3003 (see conftest.py).
    records = [_qfx_record(), _qfx_record(txn_date=date(2024, 4, 2))]
    import_transactions(conn, account_id=1, records=records)
    ids = conn.execute(
        "SELECT transaction_id FROM transactions ORDER BY transaction_id DESC LIMIT 2"
    ).fetchall()
    assert sorted(row[0] for row in ids) == [3004, 3005]


def test_import_transactions_returns_the_new_transaction_ids(conn):
    # conn fixture seeds transaction_ids up to 3003 (see conftest.py).
    records = [_qfx_record(), _qfx_record(txn_date=date(2024, 4, 2))]
    transaction_ids = import_transactions(conn, account_id=1, records=records)
    assert sorted(transaction_ids) == [3004, 3005]


def test_import_transactions_rolls_back_all_rows_on_failure(conn):
    before_count = len(data.list_transactions(conn, account_id=1))
    before_payees = data.list_payees(conn)
    records = [
        _qfx_record(name="Should Not Persist"),
        _qfx_record(txn_date=None),  # NOT NULL violation on the second row
    ]
    with pytest.raises(Exception):
        import_transactions(conn, account_id=1, records=records)
    assert len(data.list_transactions(conn, account_id=1)) == before_count
    assert data.list_payees(conn) == before_payees


def test_import_transactions_returns_empty_list_for_empty_records(conn):
    assert import_transactions(conn, account_id=1, records=[]) == []
