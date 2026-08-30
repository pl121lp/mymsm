"""Write layer for the browsing UI: money.duckdb mutation lives only here.

data.py stays read-only/query-only (see its module docstring). Every insert
here runs inside one explicit transaction so a failed write can never leave
a dictionary row (payee/category/security) without the transaction that
introduced it, or vice versa.
"""

from decimal import Decimal

from dateutils import add_months


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
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES (?, ?, ?, FALSE, ?, ?, NULL)",
        [account_id, name, account_type, opening_balance, currency],
    )
    return account_id


def update_account(conn, account_id, name, opening_balance):
    """Updates an account's name and starting (opening) balance."""
    conn.execute(
        "UPDATE accounts SET name = ?, opening_balance = ? WHERE account_id = ?",
        [name, opening_balance, account_id],
    )


def set_account_closed(conn, account_id, is_closed):
    """Sets an account's closed status. Used for both closing and reopening."""
    conn.execute(
        "UPDATE accounts SET is_closed = ? WHERE account_id = ?", [is_closed, account_id]
    )


def set_account_favorite(conn, account_id, is_favorite):
    """Sets an account's favorite status. Used for both marking and unmarking."""
    conn.execute(
        "UPDATE accounts SET is_favorite = ? WHERE account_id = ?", [is_favorite, account_id]
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


def delete_transaction(conn, transaction_id):
    """Permanently deletes a single transaction row."""
    conn.execute("DELETE FROM transactions WHERE transaction_id = ?", [transaction_id])


def restore_transaction(conn, row):
    """Re-inserts a previously-deleted transaction row exactly as captured
    by data.get_transaction_row, preserving its original transaction_id
    and dictionary ids (category_id/payee_id/security_id). Used only to
    undo delete_transaction — see ui/undo.py."""
    conn.execute(
        "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", list(row)
    )


def restore_transaction_fields(conn, row):
    """Restores the mutable fields of an existing transaction (everything
    update_transaction can change) to a previously captured snapshot, by
    raw id rather than by name — no dictionary lookup or auto-create.
    Used only to undo update_transaction — see ui/undo.py."""
    (
        transaction_id, _account_id, category_id, payee_id, txn_date, amount, memo,
        security_id, activity, quantity, price, _linked_account_id,
    ) = row
    conn.execute(
        "UPDATE transactions SET category_id = ?, payee_id = ?, txn_date = ?, amount = ?, "
        "memo = ?, security_id = ?, activity = ?, quantity = ?, price = ? "
        "WHERE transaction_id = ?",
        [category_id, payee_id, txn_date, amount, memo, security_id, activity, quantity, price, transaction_id],
    )


def delete_transactions(conn, transaction_ids):
    """Permanently deletes multiple transaction rows in one transaction —
    all-or-nothing, like import_transactions' insert side. Used only to
    undo import_transactions — see ui/undo.py."""
    if not transaction_ids:
        return
    conn.begin()
    try:
        for transaction_id in transaction_ids:
            conn.execute("DELETE FROM transactions WHERE transaction_id = ?", [transaction_id])
    except Exception:
        conn.rollback()
        raise
    conn.commit()


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
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
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


def import_transactions(conn, account_id, records):
    """Bulk-inserts parsed QFX records into account_id as plain cash rows
    (payee = record.name, memo = record.memo), auto-creating any payee that
    doesn't already exist by name (case-insensitive). The whole batch commits
    as one transaction, so a bad row can't leave the account half-imported.
    Returns the list of new transaction_ids, in insertion order."""
    if not records:
        return []
    conn.begin()
    try:
        transaction_id = _next_id(conn, "transactions", "transaction_id")
        transaction_ids = []
        for record in records:
            payee_id = _find_or_create(conn, "payees", "payee_id", record.name) if record.name else None
            conn.execute(
                "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                [
                    transaction_id, account_id, None, payee_id, record.txn_date, record.amount,
                    record.memo or None, None, None, None, None,
                ],
            )
            transaction_ids.append(transaction_id)
            transaction_id += 1
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return transaction_ids


def add_rsu_grant(
    conn, account_id, security_name, grant_date, total_shares, vest_frequency_months, vest_count,
):
    """Creates a Grant (activity 17) transaction for `total_shares` on
    `grant_date`, plus `vest_count` Vested (activity 18) transactions spaced
    `vest_frequency_months` apart, starting one interval after grant_date.
    Shares are split evenly across the vests; the last vest absorbs any
    rounding remainder so the total matches `total_shares` exactly (Money's
    own uniform-percentage rounding can drift by a share or two over a long
    schedule). Returns the new transaction_ids, grant first, then vests in
    chronological order."""
    conn.begin()
    try:
        security_id = _find_or_create(conn, "securities", "security_id", security_name)
        transaction_id = _next_id(conn, "transactions", "transaction_id")
        transaction_ids = [transaction_id]
        conn.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
            [
                transaction_id, account_id, None, None, grant_date, Decimal("0"),
                None, security_id, "17", Decimal(total_shares), Decimal("0"),
            ],
        )
        transaction_id += 1

        per_vest = total_shares // vest_count
        remainder = total_shares - per_vest * vest_count
        for i in range(1, vest_count + 1):
            quantity = per_vest + remainder if i == vest_count else per_vest
            conn.execute(
                "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                [
                    transaction_id, account_id, None, None,
                    add_months(grant_date, i * vest_frequency_months), Decimal("0"),
                    None, security_id, "18", Decimal(quantity), None,
                ],
            )
            transaction_ids.append(transaction_id)
            transaction_id += 1
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return transaction_ids


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
