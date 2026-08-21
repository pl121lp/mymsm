"""DuckDB query layer for the browsing UI. Read-only: no writes here."""

import duckdb

# Money's raw account-type code for investment accounts (see ACCOUNT_TYPE_LABELS
# in models.py). Only Buy(1)/Sell(2) activity is understood well enough to
# affect share counts; other activity codes (transfers, grants, adjustments)
# are shown in the transaction table but don't affect the computed value yet.
INVESTMENT_ACCOUNT_TYPE = "5"
BUY_ACTIVITY = "1"
SELL_ACTIVITY = "2"


def list_accounts(
    conn: duckdb.DuckDBPyConnection, include_closed: bool = False
) -> list[tuple]:
    query = """
        WITH signed_holdings AS (
            SELECT t.account_id, t.security_id, t.txn_date, t.price,
                   CASE WHEN t.activity = ? THEN -t.quantity ELSE t.quantity END AS signed_qty
            FROM transactions t
            WHERE t.security_id IS NOT NULL AND t.activity IN (?, ?)
        ),
        latest_price AS (
            SELECT account_id, security_id, price,
                   ROW_NUMBER() OVER (
                       PARTITION BY account_id, security_id ORDER BY txn_date DESC
                   ) AS rn
            FROM signed_holdings
            WHERE price IS NOT NULL
        ),
        holdings AS (
            SELECT account_id, security_id, SUM(signed_qty) AS net_qty
            FROM signed_holdings
            GROUP BY account_id, security_id
        ),
        investment_value AS (
            SELECT h.account_id, SUM(h.net_qty * lp.price) AS value
            FROM holdings h
            JOIN latest_price lp
                ON lp.account_id = h.account_id AND lp.security_id = h.security_id AND lp.rn = 1
            GROUP BY h.account_id
        ),
        cash AS (
            SELECT account_id, SUM(amount) AS total
            FROM transactions
            GROUP BY account_id
        )
        SELECT a.account_id, a.name, a.account_type, a.currency,
               CASE WHEN a.account_type = ?
                    THEN COALESCE(iv.value, 0)
                    ELSE a.opening_balance + COALESCE(cash.total, 0)
               END AS balance,
               a.is_closed
        FROM accounts a
        LEFT JOIN cash ON cash.account_id = a.account_id
        LEFT JOIN investment_value iv ON iv.account_id = a.account_id
    """
    params = [SELL_ACTIVITY, BUY_ACTIVITY, SELL_ACTIVITY, INVESTMENT_ACCOUNT_TYPE]
    if not include_closed:
        query += " WHERE a.is_closed = FALSE"
    query += """
        ORDER BY CASE a.account_type
                     WHEN '0' THEN 0
                     WHEN '1' THEN 1
                     WHEN '5' THEN 2
                     WHEN '6' THEN 3
                     WHEN '3' THEN 4
                     ELSE 5
                 END,
                 a.name
    """
    return conn.execute(query, params).fetchall()


def get_opening_balance(conn: duckdb.DuckDBPyConnection, account_id: int):
    row = conn.execute(
        "SELECT opening_balance FROM accounts WHERE account_id = ?", [account_id]
    ).fetchone()
    return row[0] if row else None


def list_transactions(conn: duckdb.DuckDBPyConnection, account_id: int) -> list[tuple]:
    query = """
        SELECT t.transaction_id, t.txn_date, p.name, c.name, t.memo, t.amount,
               sec.name, t.activity, t.quantity, t.price
        FROM transactions t
        LEFT JOIN payees p ON t.payee_id = p.payee_id
        LEFT JOIN categories c ON t.category_id = c.category_id
        LEFT JOIN securities sec ON t.security_id = sec.security_id
        WHERE t.account_id = ?
        ORDER BY t.txn_date DESC
    """
    return conn.execute(query, [account_id]).fetchall()


def search_transactions(
    conn: duckdb.DuckDBPyConnection,
    payee: str | None = None,
    category: str | None = None,
    investment: str | None = None,
    memo: str | None = None,
    amount_min=None,
    amount_max=None,
    date_min=None,
    date_max=None,
    account_ids: list[int] | None = None,
) -> list[tuple]:
    """Cross-account transaction search for the Search tab.

    Row shape matches list_transactions()'s payee/category/investment
    fields plus account_id/account_type, so results can be fed straight
    into AddRecordDialog for editing.
    """
    query = """
        SELECT t.transaction_id, t.txn_date, a.account_id, a.name, a.account_type,
               p.name, c.name, t.memo, t.amount, sec.name, t.activity, t.quantity, t.price
        FROM transactions t
        JOIN accounts a ON a.account_id = t.account_id
        LEFT JOIN payees p ON t.payee_id = p.payee_id
        LEFT JOIN categories c ON t.category_id = c.category_id
        LEFT JOIN securities sec ON t.security_id = sec.security_id
        WHERE 1 = 1
    """
    params = []
    if payee:
        query += " AND p.name ILIKE ?"
        params.append(f"%{payee}%")
    if category:
        query += " AND c.name ILIKE ?"
        params.append(f"%{category}%")
    if investment:
        query += " AND sec.name ILIKE ?"
        params.append(f"%{investment}%")
    if memo:
        query += " AND t.memo ILIKE ?"
        params.append(f"%{memo}%")
    if amount_min is not None:
        query += " AND t.amount >= ?"
        params.append(amount_min)
    if amount_max is not None:
        query += " AND t.amount <= ?"
        params.append(amount_max)
    if date_min is not None:
        query += " AND t.txn_date >= ?"
        params.append(date_min)
    if date_max is not None:
        query += " AND t.txn_date <= ?"
        params.append(date_max)
    if account_ids:
        placeholders = ",".join("?" for _ in account_ids)
        query += f" AND t.account_id IN ({placeholders})"
        params.extend(account_ids)
    query += " ORDER BY t.txn_date DESC, t.transaction_id DESC"
    return conn.execute(query, params).fetchall()


def list_categories(conn: duckdb.DuckDBPyConnection) -> list[tuple]:
    return conn.execute(
        "SELECT category_id, name FROM categories ORDER BY name"
    ).fetchall()


def list_category_transactions(
    conn: duckdb.DuckDBPyConnection, category_id: int
) -> list[tuple]:
    query = """
        SELECT t.transaction_id, t.txn_date, a.name, p.name, t.memo, t.amount
        FROM transactions t
        JOIN accounts a ON a.account_id = t.account_id
        LEFT JOIN payees p ON t.payee_id = p.payee_id
        WHERE t.category_id = ?
        ORDER BY t.txn_date DESC
    """
    return conn.execute(query, [category_id]).fetchall()


def list_payees(conn: duckdb.DuckDBPyConnection) -> list[tuple]:
    return conn.execute(
        "SELECT payee_id, name FROM payees ORDER BY name"
    ).fetchall()


def list_payee_transactions(
    conn: duckdb.DuckDBPyConnection, payee_ids: list[int]
) -> list[tuple]:
    if not payee_ids:
        return []
    placeholders = ",".join("?" for _ in payee_ids)
    query = f"""
        SELECT t.transaction_id, t.txn_date, a.name, c.name, t.memo, t.amount
        FROM transactions t
        JOIN accounts a ON a.account_id = t.account_id
        LEFT JOIN categories c ON t.category_id = c.category_id
        WHERE t.payee_id IN ({placeholders})
        ORDER BY t.txn_date DESC
    """
    return conn.execute(query, list(payee_ids)).fetchall()


def count_transactions_by_payee(conn: duckdb.DuckDBPyConnection) -> dict[int, int]:
    rows = conn.execute(
        "SELECT payee_id, COUNT(*) FROM transactions "
        "WHERE payee_id IS NOT NULL GROUP BY payee_id"
    ).fetchall()
    return dict(rows)


def list_securities(conn: duckdb.DuckDBPyConnection) -> list[tuple]:
    return conn.execute(
        "SELECT security_id, name FROM securities ORDER BY name"
    ).fetchall()


def list_security_history(
    conn: duckdb.DuckDBPyConnection, security_id: int
) -> list[tuple]:
    query = """
        WITH signed AS (
            SELECT t.transaction_id, t.account_id, a.name AS account_name,
                   t.txn_date, t.price,
                   CASE WHEN t.activity = ? THEN -t.quantity ELSE t.quantity END AS signed_qty
            FROM transactions t
            JOIN accounts a ON a.account_id = t.account_id
            WHERE t.security_id = ? AND t.activity IN (?, ?)
        )
        SELECT account_id, account_name, txn_date, price,
               SUM(signed_qty) OVER (
                   PARTITION BY account_id
                   ORDER BY txn_date, transaction_id
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               ) AS cumulative_qty
        FROM signed
        ORDER BY account_name, txn_date, transaction_id
    """
    params = [SELL_ACTIVITY, security_id, BUY_ACTIVITY, SELL_ACTIVITY]
    return conn.execute(query, params).fetchall()
