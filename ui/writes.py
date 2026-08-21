"""Write layer for the browsing UI: money.duckdb mutation lives only here.

data.py stays read-only/query-only (see its module docstring). Every insert
here runs inside one explicit transaction so a failed write can never leave
a dictionary row (payee/category/security) without the transaction that
introduced it, or vice versa.
"""


def _next_id(conn, table, id_column):
    # table/id_column are always literals from call sites in this module,
    # never user input, so this f-string is not an injection risk.
    row = conn.execute(f"SELECT MAX({id_column}) FROM {table}").fetchone()
    return (row[0] or 0) + 1


def _find_or_create(conn, table, id_column, name):
    row = conn.execute(
        f"SELECT {id_column} FROM {table} WHERE lower(name) = lower(?)", [name]
    ).fetchone()
    if row:
        return row[0]
    new_id = _next_id(conn, table, id_column)
    conn.execute(f"INSERT INTO {table} VALUES (?, ?)", [new_id, name])
    return new_id


def add_account(conn, name, account_type, currency, opening_balance):
    """Inserts a new account row (open by default). Returns the new account_id."""
    account_id = _next_id(conn, "accounts", "account_id")
    conn.execute(
        "INSERT INTO accounts VALUES (?, ?, ?, FALSE, ?, ?)",
        [account_id, name, account_type, opening_balance, currency],
    )
    return account_id


def set_account_closed(conn, account_id, is_closed):
    """Sets an account's closed status. Used for both closing and reopening."""
    conn.execute(
        "UPDATE accounts SET is_closed = ? WHERE account_id = ?", [is_closed, account_id]
    )


def delete_account(conn, account_id):
    """Permanently deletes an account and its transactions (the transactions
    FK has no cascade, so they must be removed first).

    Not wrapped in an explicit transaction: DuckDB's FK constraint check on
    the second DELETE does not see the first DELETE's effect within the same
    uncommitted transaction (a documented DuckDB FK limitation), so each
    statement is left to auto-commit individually.
    """
    conn.execute("DELETE FROM transactions WHERE account_id = ?", [account_id])
    conn.execute("DELETE FROM accounts WHERE account_id = ?", [account_id])


def add_transaction(
    conn,
    account_id,
    txn_date,
    amount,
    memo=None,
    payee_name=None,
    category_name=None,
    security_name=None,
    activity=None,
    quantity=None,
    price=None,
):
    """Inserts a transaction row, auto-creating any named dictionary entry
    (payee/category/security) that doesn't already exist by name (case-
    insensitive). Returns the new transaction_id. Rolls back entirely (no
    partial dictionary rows) if the transaction insert itself fails."""
    conn.begin()
    try:
        payee_id = _find_or_create(conn, "payees", "payee_id", payee_name) if payee_name else None
        category_id = (
            _find_or_create(conn, "categories", "category_id", category_name)
            if category_name
            else None
        )
        security_id = (
            _find_or_create(conn, "securities", "security_id", security_name)
            if security_name
            else None
        )
        transaction_id = _next_id(conn, "transactions", "transaction_id")
        conn.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                transaction_id, account_id, category_id, payee_id, txn_date, amount,
                memo, security_id, activity, quantity, price,
            ],
        )
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return transaction_id


def update_transaction(
    conn,
    transaction_id,
    txn_date,
    amount,
    memo=None,
    payee_name=None,
    category_name=None,
    security_name=None,
    activity=None,
    quantity=None,
    price=None,
):
    """Updates an existing transaction row in place, auto-creating any named
    dictionary entry (payee/category/security) that doesn't already exist by
    name (case-insensitive). Returns transaction_id. Rolls back entirely (no
    partial dictionary rows) if the update itself fails."""
    conn.begin()
    try:
        payee_id = _find_or_create(conn, "payees", "payee_id", payee_name) if payee_name else None
        category_id = (
            _find_or_create(conn, "categories", "category_id", category_name)
            if category_name
            else None
        )
        security_id = (
            _find_or_create(conn, "securities", "security_id", security_name)
            if security_name
            else None
        )
        conn.execute(
            "UPDATE transactions SET category_id = ?, payee_id = ?, txn_date = ?, amount = ?, "
            "memo = ?, security_id = ?, activity = ?, quantity = ?, price = ? "
            "WHERE transaction_id = ?",
            [
                category_id, payee_id, txn_date, amount,
                memo, security_id, activity, quantity, price, transaction_id,
            ],
        )
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return transaction_id
