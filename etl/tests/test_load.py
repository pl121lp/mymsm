from datetime import date
from decimal import Decimal
from pathlib import Path

import duckdb

from load import load

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_writes_expected_row_counts(tmp_path):
    db_path = tmp_path / "test.duckdb"
    summary = load(FIXTURES, db_path)
    assert summary == {
        "accounts": 8,
        "categories": 2,
        "payees": 2,
        "securities": 2,
        "transactions": 10,
    }
    assert db_path.exists()


def test_load_resolves_account_currency(tmp_path):
    db_path = tmp_path / "test.duckdb"
    load(FIXTURES, db_path)
    conn = duckdb.connect(str(db_path))
    try:
        savings = conn.execute(
            "SELECT currency FROM accounts WHERE account_id = 2"
        ).fetchone()
        old_card = conn.execute(
            "SELECT currency FROM accounts WHERE account_id = 3"
        ).fetchone()
    finally:
        conn.close()
    assert savings == ("SEK",)
    assert old_card == ("USD",)


def test_load_resolves_investment_transaction_details(tmp_path):
    db_path = tmp_path / "test.duckdb"
    load(FIXTURES, db_path)
    conn = duckdb.connect(str(db_path))
    try:
        row = conn.execute(
            "SELECT s.name, t.activity, t.quantity, t.price "
            "FROM transactions t JOIN securities s ON s.security_id = t.security_id "
            "WHERE t.transaction_id = 2000"
        ).fetchone()
    finally:
        conn.close()
    assert row == ("Vanguard Total Stock Market Index", "1", Decimal("8.0"), Decimal("18.39"))


def test_load_resolves_loan_interest_and_linked_account_fields(tmp_path):
    db_path = tmp_path / "test.duckdb"
    load(FIXTURES, db_path)
    conn = duckdb.connect(str(db_path))
    try:
        car_loan = conn.execute(
            "SELECT interest_category_id FROM accounts WHERE account_id = 5"
        ).fetchone()
        principal = conn.execute(
            "SELECT linked_account_id FROM transactions WHERE transaction_id = 3000"
        ).fetchone()
    finally:
        conn.close()
    assert car_loan == (10,)
    assert principal == (1,)


def test_load_resolves_date_opened(tmp_path):
    db_path = tmp_path / "test.duckdb"
    load(FIXTURES, db_path)
    conn = duckdb.connect(str(db_path))
    try:
        checking = conn.execute(
            "SELECT date_opened FROM accounts WHERE account_id = 1"
        ).fetchone()
        old_card = conn.execute(
            "SELECT date_opened FROM accounts WHERE account_id = 3"
        ).fetchone()
    finally:
        conn.close()
    assert checking == (date(2020, 1, 1),)
    assert old_card == (None,)


def test_load_resolves_loan_terms(tmp_path):
    db_path = tmp_path / "test.duckdb"
    load(FIXTURES, db_path)
    conn = duckdb.connect(str(db_path))
    try:
        car_loan = conn.execute(
            "SELECT loan_interest_rate, loan_payment_amount, loan_payment_count "
            "FROM accounts WHERE account_id = 5"
        ).fetchone()
    finally:
        conn.close()
    assert car_loan == (Decimal("0.05"), Decimal("250.00"), 48)
