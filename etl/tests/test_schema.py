import duckdb

from schema import apply_schema


def test_apply_schema_creates_expected_tables():
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
    assert tables == {"accounts", "categories", "payees", "transactions", "securities"}


def test_accounts_table_has_opening_balance_column():
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info('accounts')").fetchall()}
    assert "opening_balance" in columns


def test_accounts_table_currency_column_defaults_to_usd():
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance) "
        "VALUES (1, 'Checking', 'Bank', FALSE, 0)"
    )
    assert conn.execute("SELECT currency FROM accounts WHERE account_id = 1").fetchone() == ("USD",)


def test_securities_table_has_id_and_name_columns():
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info('securities')").fetchall()}
    assert {"security_id", "name"} <= columns


def test_transactions_table_has_investment_columns():
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info('transactions')").fetchall()}
    assert {"security_id", "activity", "quantity", "price"} <= columns
