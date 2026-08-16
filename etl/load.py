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
from transform import build_accounts, build_categories, build_payees, build_transactions


def load(raw_dir: Path, db_path: Path) -> dict:
    accounts = build_accounts(raw_dir)
    categories = build_categories(raw_dir)
    payees = build_payees(raw_dir)
    transactions = build_transactions(
        raw_dir,
        known_account_ids={a["account_id"] for a in accounts},
        known_category_ids={c["category_id"] for c in categories},
        known_payee_ids={p["payee_id"] for p in payees},
    )

    if db_path.exists():
        db_path.unlink()

    conn = duckdb.connect(str(db_path))
    try:
        apply_schema(conn)
        conn.executemany(
            "INSERT INTO accounts VALUES (?, ?, ?, ?)",
            [(a["account_id"], a["name"], a["account_type"], a["is_closed"]) for a in accounts],
        )
        conn.executemany(
            "INSERT INTO categories VALUES (?, ?)",
            [(c["category_id"], c["name"]) for c in categories],
        )
        conn.executemany(
            "INSERT INTO payees VALUES (?, ?)",
            [(p["payee_id"], p["name"]) for p in payees],
        )
        conn.executemany(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    t["transaction_id"], t["account_id"], t["category_id"], t["payee_id"],
                    t["txn_date"], t["amount"], t["memo"],
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
