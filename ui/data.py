"""DuckDB query layer for the browsing UI. Read-only: no writes here."""

import duckdb

# Money's raw account-type code for investment accounts (see ACCOUNT_TYPE_LABELS
# in models.py). Only Buy(1)/Sell(2) activity is understood well enough to
# affect share counts; other activity codes (transfers, grants, adjustments)
# are shown in the transaction table but don't affect the computed value yet.
INVESTMENT_ACCOUNT_TYPE = "5"
LOAN_ACCOUNT_TYPE = "6"
ASSET_ACCOUNT_TYPE = "3"
BUY_ACTIVITY = "1"
SELL_ACTIVITY = "2"
# RSU-specific activity codes Money uses for grant/vest/sell/expiration
# events (17-20). A grant (17) is unvested and doesn't affect holdings;
# vested shares (18) add to holdings like a buy; RSU sales (19) subtract
# like a sell; expiration (20) is never relevant to a share count.
VEST_ACTIVITY = "18"
RSU_SELL_ACTIVITY = "19"


def list_accounts(
    conn: duckdb.DuckDBPyConnection, include_closed: bool = False, only_closed: bool = False
) -> list[tuple]:
    query = """
        WITH signed_holdings AS (
            SELECT t.account_id, t.security_id, t.txn_date, t.price,
                   CASE WHEN t.activity IN (?, ?) THEN -t.quantity ELSE t.quantity END AS signed_qty
            FROM transactions t
            WHERE t.security_id IS NOT NULL AND t.activity IN (?, ?, ?, ?)
                  AND t.txn_date <= CURRENT_DATE
        ),
        latest_price AS (
            SELECT account_id, security_id, price,
                   ROW_NUMBER() OVER (
                       PARTITION BY account_id, security_id ORDER BY txn_date DESC
                   ) AS rn
            FROM signed_holdings
            WHERE price IS NOT NULL AND price > 0
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
    params = [
        SELL_ACTIVITY, RSU_SELL_ACTIVITY,
        BUY_ACTIVITY, SELL_ACTIVITY, VEST_ACTIVITY, RSU_SELL_ACTIVITY,
        INVESTMENT_ACCOUNT_TYPE,
    ]
    if only_closed:
        query += " WHERE a.is_closed = TRUE"
    elif not include_closed:
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


def get_loan_terms(conn: duckdb.DuckDBPyConnection, account_id: int) -> tuple | None:
    """(interest_rate, payment_amount, payment_count) for a loan account,
    as imported from Money -- interest_rate is a fraction (e.g. 0.05 for
    5%), payment_amount is the positive principal+interest installment.
    Any field may individually be None if that data wasn't available in
    the source. Returns None only if the account itself doesn't exist."""
    return conn.execute(
        "SELECT loan_interest_rate, loan_payment_amount, loan_payment_count "
        "FROM accounts WHERE account_id = ?", [account_id],
    ).fetchone()


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


def get_transaction_row(conn: duckdb.DuckDBPyConnection, transaction_id: int) -> tuple | None:
    """Raw (unjoined) transaction row, ids not names — a snapshot used by
    ui/undo.py to reverse an edit or delete. Column order matches the
    transactions table exactly (see etl/schema.py)."""
    return conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = ?",
        [transaction_id],
    ).fetchone()


def list_loan_interest_payments(conn: duckdb.DuckDBPyConnection, account_id: int) -> list[tuple]:
    """Reconstructed interest payments for a loan account, as
    (txn_date, payee, amount, currency) — currency is the *paying* account's,
    which may differ from the loan account's own currency.

    Money never posts interest to the loan account itself: a loan payment is
    a split transaction whose Principal leg transfers into the loan account
    (recorded here as a transaction with linked_account_id pointing at the
    paying account) while its Interest leg stays on the paying account,
    categorized under the loan's interest_category_id. This reconstructs the
    payments by grouping this account's Principal legs by (paying account,
    payee, date) and summing whatever the paying account posted under that
    category for the same payee/date — filtering out any other same-day
    split (e.g. escrow) under a different category. Payee is matched with
    IS NOT DISTINCT FROM since both legs are commonly payee-less transfers,
    and plain `=` never matches NULL against NULL. Amount is returned
    positive (interest paid), most recent first.
    """
    query = """
        WITH principal AS (
            SELECT DISTINCT t.linked_account_id, t.payee_id, t.txn_date
            FROM transactions t
            WHERE t.account_id = ? AND t.linked_account_id IS NOT NULL
        )
        SELECT p.txn_date, py.name, -SUM(i.amount) AS interest_amount, a.currency
        FROM principal p
        JOIN transactions i
            ON i.account_id = p.linked_account_id
           AND i.payee_id IS NOT DISTINCT FROM p.payee_id
           AND i.txn_date = p.txn_date
           AND i.category_id = (SELECT interest_category_id FROM accounts WHERE account_id = ?)
        JOIN accounts a ON a.account_id = p.linked_account_id
        LEFT JOIN payees py ON py.payee_id = p.payee_id
        GROUP BY p.txn_date, py.name, a.currency
        ORDER BY p.txn_date DESC
    """
    return conn.execute(query, [account_id, account_id]).fetchall()


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


def list_category_spending(conn: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Every categorized transaction across all accounts, for the spending-by-category report.

    Uncategorized transactions (including investment buy/sell activity, which
    has no category_id) are excluded.
    """
    query = """
        SELECT c.category_id, c.name, t.txn_date, t.amount, a.currency
        FROM transactions t
        JOIN accounts a ON a.account_id = t.account_id
        JOIN categories c ON c.category_id = t.category_id
        ORDER BY t.txn_date
    """
    return conn.execute(query).fetchall()


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


def count_transactions_by_category(conn: duckdb.DuckDBPyConnection) -> dict[int, int]:
    rows = conn.execute(
        "SELECT category_id, COUNT(*) FROM transactions "
        "WHERE category_id IS NOT NULL GROUP BY category_id"
    ).fetchall()
    return dict(rows)


def list_securities(conn: duckdb.DuckDBPyConnection) -> list[tuple]:
    return conn.execute(
        "SELECT security_id, name FROM securities ORDER BY name"
    ).fetchall()


def list_investment_prices(conn: duckdb.DuckDBPyConnection) -> list[tuple]:
    """Every priced Buy/Sell trade across all accounts, for the investment
    analysis report. Rows are (security_name, txn_date, price)."""
    query = """
        SELECT s.name, t.txn_date, t.price
        FROM transactions t
        JOIN securities s ON s.security_id = t.security_id
        WHERE t.activity IN (?, ?, ?) AND t.price IS NOT NULL AND t.price > 0
        ORDER BY s.name, t.txn_date
    """
    return conn.execute(query, [BUY_ACTIVITY, SELL_ACTIVITY, RSU_SELL_ACTIVITY]).fetchall()


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
