"""DuckDB query layer for the browsing UI. Read-only: no writes here."""

import duckdb


def list_accounts(
    conn: duckdb.DuckDBPyConnection, include_closed: bool = False
) -> list[tuple]:
    query = "SELECT account_id, name, account_type FROM accounts"
    if not include_closed:
        query += " WHERE is_closed = FALSE"
    query += " ORDER BY name"
    return conn.execute(query).fetchall()


def list_transactions(conn: duckdb.DuckDBPyConnection, account_id: int) -> list[tuple]:
    query = """
        SELECT t.transaction_id, t.txn_date, p.name, c.name, t.memo, t.amount
        FROM transactions t
        LEFT JOIN payees p ON t.payee_id = p.payee_id
        LEFT JOIN categories c ON t.category_id = c.category_id
        WHERE t.account_id = ?
        ORDER BY t.txn_date DESC
    """
    return conn.execute(query, [account_id]).fetchall()
