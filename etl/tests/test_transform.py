from pathlib import Path

from transform import build_accounts, build_categories, build_payees, build_transactions

FIXTURES = Path(__file__).parent / "fixtures"


def test_build_accounts():
    accounts = build_accounts(FIXTURES)
    assert len(accounts) == 3
    checking = next(a for a in accounts if a["account_id"] == 1)
    assert checking["name"] == "Checking"
    assert checking["is_closed"] is False
    old_card = next(a for a in accounts if a["account_id"] == 3)
    assert old_card["is_closed"] is True


def test_build_categories():
    categories = build_categories(FIXTURES)
    assert {c["category_id"] for c in categories} == {10, 11}


def test_build_payees():
    payees = build_payees(FIXTURES)
    assert {p["payee_id"] for p in payees} == {100, 101}


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
