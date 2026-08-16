"""Reads Money's raw exported CSV tables and builds normalized rows for
loading into DuckDB. Defensive: rows that don't match the expected shape
are logged and skipped rather than aborting the whole load.
"""

import csv
import logging
from pathlib import Path
from typing import Optional

from column_map import ACCOUNTS, CATEGORIES, PAYEES, TRANSACTIONS
from moneytypes import convert_currency, convert_date

logger = logging.getLogger(__name__)


def read_raw_table(raw_dir: Path, table_name: str) -> list[dict]:
    path = raw_dir / f"{table_name}.csv"
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _to_int(raw: Optional[str]) -> Optional[int]:
    if raw is None or raw.strip() == "":
        return None
    try:
        return int(float(raw))
    except ValueError:
        return None


def build_accounts(raw_dir: Path) -> list[dict]:
    rows = read_raw_table(raw_dir, ACCOUNTS["table"])
    result = []
    skipped = 0
    for row in rows:
        account_id = _to_int(row.get(ACCOUNTS["id"]))
        name = row.get(ACCOUNTS["name"])
        if account_id is None or not name:
            skipped += 1
            continue
        result.append({
            "account_id": account_id,
            "name": name,
            "account_type": row.get(ACCOUNTS["account_type"]) or None,
            "is_closed": (row.get(ACCOUNTS["is_closed"]) or "").strip() in ("1", "true", "True"),
        })
    logger.info("accounts: built %d, skipped %d", len(result), skipped)
    return result


def build_categories(raw_dir: Path) -> list[dict]:
    rows = read_raw_table(raw_dir, CATEGORIES["table"])
    result = []
    skipped = 0
    for row in rows:
        category_id = _to_int(row.get(CATEGORIES["id"]))
        name = row.get(CATEGORIES["name"])
        if category_id is None or not name:
            skipped += 1
            continue
        result.append({"category_id": category_id, "name": name})
    logger.info("categories: built %d, skipped %d", len(result), skipped)
    return result


def build_payees(raw_dir: Path) -> list[dict]:
    rows = read_raw_table(raw_dir, PAYEES["table"])
    result = []
    skipped = 0
    for row in rows:
        payee_id = _to_int(row.get(PAYEES["id"]))
        name = row.get(PAYEES["name"])
        if payee_id is None or not name:
            skipped += 1
            continue
        result.append({"payee_id": payee_id, "name": name})
    logger.info("payees: built %d, skipped %d", len(result), skipped)
    return result


def build_transactions(
    raw_dir: Path,
    known_account_ids: set[int],
    known_category_ids: set[int],
    known_payee_ids: set[int],
) -> list[dict]:
    rows = read_raw_table(raw_dir, TRANSACTIONS["table"])
    result = []
    skipped = 0
    for row in rows:
        txn_id = _to_int(row.get(TRANSACTIONS["id"]))
        account_id = _to_int(row.get(TRANSACTIONS["account_id"]))
        raw_date = row.get(TRANSACTIONS["date"])
        raw_amount = row.get(TRANSACTIONS["amount"])

        if txn_id is None or account_id is None or account_id not in known_account_ids:
            skipped += 1
            continue
        if not raw_date or not raw_amount:
            skipped += 1
            continue

        try:
            txn_date = convert_date(raw_date)
            amount = convert_currency(raw_amount)
        except ValueError:
            skipped += 1
            continue

        category_id = _to_int(row.get(TRANSACTIONS["category_id"]))
        if category_id is not None and category_id not in known_category_ids:
            category_id = None

        payee_id = _to_int(row.get(TRANSACTIONS["payee_id"]))
        if payee_id is not None and payee_id not in known_payee_ids:
            payee_id = None

        result.append({
            "transaction_id": txn_id,
            "account_id": account_id,
            "category_id": category_id,
            "payee_id": payee_id,
            "txn_date": txn_date,
            "amount": amount,
            "memo": row.get(TRANSACTIONS["memo"]) or None,
        })
    logger.info("transactions: built %d, skipped %d", len(result), skipped)
    return result
