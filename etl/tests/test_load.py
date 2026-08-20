from decimal import Decimal
from pathlib import Path

import duckdb

from load import load

FIXTURES = Path(__file__).parent / "fixtures"


def test_load_writes_expected_row_counts(tmp_path):
    db_path = tmp_path / "test.duckdb"
    summary = load(FIXTURES, db_path)
    assert summary == {
        "accounts": 4,
        "categories": 2,
        "payees": 2,
        "securities": 2,
        "transactions": 8,
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
