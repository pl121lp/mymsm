from decimal import Decimal
from pathlib import Path

from transform import (
    build_accounts,
    build_categories,
    build_currencies,
    build_payees,
    build_securities,
    build_transactions,
)

FIXTURES = Path(__file__).parent / "fixtures"


def test_build_accounts():
    accounts = build_accounts(FIXTURES)
    assert len(accounts) == 4
    checking = next(a for a in accounts if a["account_id"] == 1)
    assert checking["name"] == "Checking"
    assert checking["is_closed"] is False
    old_card = next(a for a in accounts if a["account_id"] == 3)
    assert old_card["is_closed"] is True


def test_build_currencies_maps_id_to_iso_code():
    currencies = build_currencies(FIXTURES)
    assert currencies == {38: "SEK", 45: "USD"}


def test_build_accounts_resolves_currency_from_currencies_map():
    currencies = build_currencies(FIXTURES)
    accounts = build_accounts(FIXTURES, currencies)
    savings = next(a for a in accounts if a["account_id"] == 2)
    assert savings["currency"] == "SEK"


def test_build_accounts_defaults_missing_currency_to_usd():
    currencies = build_currencies(FIXTURES)
    accounts = build_accounts(FIXTURES, currencies)
    old_card = next(a for a in accounts if a["account_id"] == 3)
    assert old_card["currency"] == "USD"


def test_build_accounts_defaults_currency_to_usd_when_no_currencies_map_given():
    accounts = build_accounts(FIXTURES)
    checking = next(a for a in accounts if a["account_id"] == 1)
    assert checking["currency"] == "USD"


def test_build_accounts_parses_opening_balance():
    accounts = build_accounts(FIXTURES)
    checking = next(a for a in accounts if a["account_id"] == 1)
    assert str(checking["opening_balance"]) == "100.00"


def test_build_accounts_defaults_missing_opening_balance_to_zero():
    accounts = build_accounts(FIXTURES)
    old_card = next(a for a in accounts if a["account_id"] == 3)
    assert old_card["opening_balance"] == Decimal("0")


def test_build_categories():
    categories = build_categories(FIXTURES)
    assert {c["category_id"] for c in categories} == {10, 11}


def test_build_payees():
    payees = build_payees(FIXTURES)
    assert {p["payee_id"] for p in payees} == {100, 101}


def test_build_securities():
    securities = build_securities(FIXTURES)
    assert {s["security_id"] for s in securities} == {50, 51}
    vanguard = next(s for s in securities if s["security_id"] == 50)
    assert vanguard["name"] == "Vanguard Total Stock Market Index"


def test_build_transactions_resolves_known_ids_and_amount():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
    )
    ids = {t["transaction_id"] for t in transactions}
    assert ids == {1000, 1001, 1002}
    groceries = next(t for t in transactions if t["transaction_id"] == 1000)
    assert str(groceries["amount"]) == "-52.30"
    assert groceries["category_id"] == 10


def test_build_transactions_resolves_payee_and_memo():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
    )
    groceries = next(t for t in transactions if t["transaction_id"] == 1000)
    assert groceries["payee_id"] == 100
    assert groceries["memo"] == "Weekly groceries"


def test_build_transactions_nulls_unknown_category():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
    )
    unknown_cat_txn = next(t for t in transactions if t["transaction_id"] == 1002)
    assert unknown_cat_txn["category_id"] is None


def test_build_transactions_skips_unknown_account():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
    )
    assert all(t["transaction_id"] != 1003 for t in transactions)


def test_build_transactions_skips_malformed_account_id():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
    )
    assert all(t["transaction_id"] != 1004 for t in transactions)


def test_build_transactions_skips_malformed_amount():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
    )
    assert all(t["transaction_id"] != 1005 for t in transactions)


def test_build_transactions_leaves_investment_fields_null_for_non_investment_txn():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
    )
    groceries = next(t for t in transactions if t["transaction_id"] == 1000)
    assert groceries["security_id"] is None
    assert groceries["activity"] is None
    assert groceries["quantity"] is None
    assert groceries["price"] is None


def test_build_transactions_resolves_investment_fields():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3, 4},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
        known_security_ids={50, 51},
    )
    buy = next(t for t in transactions if t["transaction_id"] == 2000)
    assert buy["security_id"] == 50
    assert buy["activity"] == "1"
    assert buy["quantity"] == Decimal("8.0")
    assert buy["price"] == Decimal("18.39")


def test_build_transactions_nulls_unknown_security_but_keeps_quantity_and_price():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3, 4},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
        known_security_ids={50, 51},
    )
    unknown_sec_txn = next(t for t in transactions if t["transaction_id"] == 2004)
    assert unknown_sec_txn["security_id"] is None
    assert unknown_sec_txn["quantity"] == Decimal("0.5")
    assert unknown_sec_txn["price"] == Decimal("10.0")


def test_build_transactions_handles_missing_price():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3, 4},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
        known_security_ids={50, 51},
    )
    grant = next(t for t in transactions if t["transaction_id"] == 2003)
    assert grant["price"] is None
    assert grant["quantity"] == Decimal("20.0")
