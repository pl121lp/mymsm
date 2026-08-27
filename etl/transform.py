"""Reads Money's raw exported CSV tables and builds normalized rows for
loading into DuckDB. Defensive: rows that don't match the expected shape
are logged and skipped rather than aborting the whole load.
"""

import csv
import logging
from pathlib import Path
from typing import Optional

from decimal import Decimal, InvalidOperation

from column_map import (
    ACCOUNTS,
    CATEGORIES,
    CURRENCIES,
    PAYEES,
    SECURITIES,
    TRANSACTION_INVESTMENTS,
    TRANSACTIONS,
)
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


def _to_decimal(raw: Optional[str]) -> Optional[Decimal]:
    if raw is None or raw.strip() == "":
        return None
    try:
        return Decimal(raw)
    except InvalidOperation:
        return None


PRIMARY_CURRENCY = "USD"


def _to_loan_rate(raw_primary: Optional[str], raw_fallback: Optional[str]) -> Optional[Decimal]:
    """rateUser/rateCalc are plain percentages (e.g. "5.0" for 5%);
    returns the fraction (Decimal("0.05")), preferring raw_primary and
    only using raw_fallback when raw_primary is absent. Explicit None
    checks throughout (not truthiness) so a legitimate 0% rate is never
    mistaken for "missing"."""
    rate = _to_decimal(raw_primary)
    if rate is None:
        rate = _to_decimal(raw_fallback)
    if rate is None:
        return None
    return rate / Decimal(100)


def build_currencies(raw_dir: Path) -> dict[int, str]:
    rows = read_raw_table(raw_dir, CURRENCIES["table"])
    result = {}
    for row in rows:
        currency_id = _to_int(row.get(CURRENCIES["id"]))
        iso_code = row.get(CURRENCIES["iso_code"])
        if currency_id is None or not iso_code:
            continue
        result[currency_id] = iso_code
    return result


def build_accounts(
    raw_dir: Path,
    currencies: Optional[dict[int, str]] = None,
    known_category_ids: Optional[set[int]] = None,
) -> list[dict]:
    currencies = currencies or {}
    known_category_ids = known_category_ids or set()
    rows = read_raw_table(raw_dir, ACCOUNTS["table"])
    result = []
    skipped = 0
    for row in rows:
        account_id = _to_int(row.get(ACCOUNTS["id"]))
        name = row.get(ACCOUNTS["name"])
        if account_id is None or not name:
            skipped += 1
            continue
        try:
            opening_balance = convert_currency(row.get(ACCOUNTS["opening_balance"]) or "")
        except ValueError:
            opening_balance = Decimal("0")
        try:
            date_opened = convert_date(row.get(ACCOUNTS["date_opened"]) or "")
        except ValueError:
            date_opened = None
        currency_id = _to_int(row.get(ACCOUNTS["currency"]))
        interest_category_id = _to_int(row.get(ACCOUNTS["interest_category"]))
        if interest_category_id not in known_category_ids:
            interest_category_id = None
        loan_payment_amount = _to_decimal(row.get(ACCOUNTS["loan_payment_amount"]))
        result.append({
            "account_id": account_id,
            "name": name,
            "account_type": row.get(ACCOUNTS["account_type"]) or None,
            "is_closed": (row.get(ACCOUNTS["is_closed"]) or "").strip() in ("1", "true", "True"),
            "opening_balance": opening_balance,
            "date_opened": date_opened,
            "currency": currencies.get(currency_id, PRIMARY_CURRENCY),
            "interest_category_id": interest_category_id,
            "loan_interest_rate": _to_loan_rate(
                row.get(ACCOUNTS["loan_interest_rate"]), row.get(ACCOUNTS["loan_interest_rate_fallback"])
            ),
            "loan_payment_amount": abs(loan_payment_amount) if loan_payment_amount is not None else None,
            "loan_payment_count": _to_int(row.get(ACCOUNTS["loan_payment_count"])),
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


def build_securities(raw_dir: Path) -> list[dict]:
    rows = read_raw_table(raw_dir, SECURITIES["table"])
    result = []
    skipped = 0
    for row in rows:
        security_id = _to_int(row.get(SECURITIES["id"]))
        name = row.get(SECURITIES["name"])
        if security_id is None or not name:
            skipped += 1
            continue
        result.append({"security_id": security_id, "name": name})
    logger.info("securities: built %d, skipped %d", len(result), skipped)
    return result


def _read_investment_details(raw_dir: Path) -> dict[int, dict]:
    rows = read_raw_table(raw_dir, TRANSACTION_INVESTMENTS["table"])
    result = {}
    for row in rows:
        txn_id = _to_int(row.get(TRANSACTION_INVESTMENTS["id"]))
        if txn_id is None:
            continue
        result[txn_id] = {
            "quantity": _to_decimal(row.get(TRANSACTION_INVESTMENTS["quantity"])),
            "price": _to_decimal(row.get(TRANSACTION_INVESTMENTS["price"])),
        }
    return result


def build_transactions(
    raw_dir: Path,
    known_account_ids: set[int],
    known_category_ids: set[int],
    known_payee_ids: set[int],
    known_security_ids: set[int] = frozenset(),
) -> list[dict]:
    rows = read_raw_table(raw_dir, TRANSACTIONS["table"])
    investment_details = _read_investment_details(raw_dir)
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

        security_id = _to_int(row.get(TRANSACTIONS["security_id"]))
        if security_id is not None and security_id not in known_security_ids:
            security_id = None

        linked_account_id = _to_int(row.get(TRANSACTIONS["linked_account_id"]))
        if linked_account_id is not None and linked_account_id not in known_account_ids:
            linked_account_id = None

        details = investment_details.get(txn_id, {})

        result.append({
            "transaction_id": txn_id,
            "account_id": account_id,
            "category_id": category_id,
            "payee_id": payee_id,
            "txn_date": txn_date,
            "amount": amount,
            "memo": row.get(TRANSACTIONS["memo"]) or None,
            "security_id": security_id,
            "activity": row.get(TRANSACTIONS["activity"]) or None,
            "quantity": details.get("quantity"),
            "price": details.get("price"),
            "linked_account_id": linked_account_id,
        })
    logger.info("transactions: built %d, skipped %d", len(result), skipped)
    return result
