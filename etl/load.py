"""Loads Money data from raw exported CSVs (produced by extract-mny) into
a DuckDB database.

Usage:
    python load.py <raw_dir> <output_duckdb_path>
"""

import logging
import sys
from pathlib import Path

import duckdb

from schema import apply_schema
from transform import (
    build_accounts,
    build_categories,
    build_currencies,
    build_payees,
    build_securities,
    build_transactions,
)


def load(raw_dir: Path, db_path: Path) -> dict:
    currencies = build_currencies(raw_dir)
    categories = build_categories(raw_dir)
    accounts = build_accounts(
        raw_dir, currencies, known_category_ids={c["category_id"] for c in categories}
    )
    payees = build_payees(raw_dir)
    securities = build_securities(raw_dir)
    transactions = build_transactions(
        raw_dir,
        known_account_ids={a["account_id"] for a in accounts},
        known_category_ids={c["category_id"] for c in categories},
        known_payee_ids={p["payee_id"] for p in payees},
        known_security_ids={s["security_id"] for s in securities},
    )

    if db_path.exists():
        db_path.unlink()

    conn = duckdb.connect(str(db_path))
    try:
        apply_schema(conn)
        conn.executemany(
            "INSERT INTO categories VALUES (?, ?)",
            [(c["category_id"], c["name"]) for c in categories],
        )
        conn.executemany(
            "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
            "currency, interest_category_id, loan_interest_rate, loan_payment_amount, "
            "loan_payment_count, date_opened) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    a["account_id"], a["name"], a["account_type"], a["is_closed"],
                    a["opening_balance"], a["currency"], a["interest_category_id"],
                    a["loan_interest_rate"], a["loan_payment_amount"], a["loan_payment_count"],
                    a["date_opened"],
                )
                for a in accounts
            ],
        )
        conn.executemany(
            "INSERT INTO payees VALUES (?, ?)",
            [(p["payee_id"], p["name"]) for p in payees],
        )
        conn.executemany(
            "INSERT INTO securities VALUES (?, ?)",
            [(s["security_id"], s["name"]) for s in securities],
        )
        conn.executemany(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    t["transaction_id"], t["account_id"], t["category_id"], t["payee_id"],
                    t["txn_date"], t["amount"], t["memo"], t["security_id"], t["activity"],
                    t["quantity"], t["price"], t["linked_account_id"],
                )
                for t in transactions
            ],
        )
    finally:
        conn.close()

    return {
        "accounts": len(accounts),
        "categories": len(categories),
        "payees": len(payees),
        "securities": len(securities),
        "transactions": len(transactions),
    }


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if len(sys.argv) != 3:
        print("Usage: python load.py <raw_dir> <output_duckdb_path>")
        sys.exit(2)

    raw_dir = Path(sys.argv[1])
    db_path = Path(sys.argv[2])
    summary = load(raw_dir, db_path)

    print("Loaded into", db_path)
    for table, count in summary.items():
        print(f"  {table}: {count} rows")


if __name__ == "__main__":
    main()
