from datetime import date
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
    assert len(accounts) == 8
    checking = next(a for a in accounts if a["account_id"] == 1)
    assert checking["name"] == "Checking"
    assert checking["is_closed"] is False
    old_card = next(a for a in accounts if a["account_id"] == 3)
    assert old_card["is_closed"] is True


def test_build_accounts_aliases_type_2_to_checking_savings():
    accounts = build_accounts(FIXTURES)
    cash_fund = next(a for a in accounts if a["account_id"] == 7)
    assert cash_fund["account_type"] == "0"


def test_build_accounts_aliases_type_4_to_loan():
    accounts = build_accounts(FIXTURES)
    old_loan = next(a for a in accounts if a["account_id"] == 8)
    assert old_loan["account_type"] == "6"


def test_build_accounts_hides_type_8_accounts():
    accounts = build_accounts(FIXTURES)
    assert all(a["account_id"] != 9 for a in accounts)


def test_build_accounts_resolves_interest_category_id_when_known():
    accounts = build_accounts(FIXTURES, known_category_ids={10, 11})
    car_loan = next(a for a in accounts if a["account_id"] == 5)
    assert car_loan["interest_category_id"] == 10


def test_build_accounts_nulls_interest_category_id_when_unknown():
    accounts = build_accounts(FIXTURES, known_category_ids={10, 11})
    old_mortgage = next(a for a in accounts if a["account_id"] == 6)
    assert old_mortgage["interest_category_id"] is None


def test_build_accounts_nulls_interest_category_id_without_known_category_ids():
    accounts = build_accounts(FIXTURES)
    car_loan = next(a for a in accounts if a["account_id"] == 5)
    assert car_loan["interest_category_id"] is None


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


def test_build_accounts_parses_date_opened():
    accounts = build_accounts(FIXTURES)
    checking = next(a for a in accounts if a["account_id"] == 1)
    assert checking["date_opened"] == date(2020, 1, 1)


def test_build_accounts_treats_blank_date_opened_as_none():
    accounts = build_accounts(FIXTURES)
    old_card = next(a for a in accounts if a["account_id"] == 3)
    assert old_card["date_opened"] is None


def test_build_accounts_treats_moneys_unset_date_sentinel_as_none():
    # Money represents "never set" dates as a far-future sentinel
    # (+10000-02-28) rather than leaving the field blank.
    accounts = build_accounts(FIXTURES)
    old_mortgage = next(a for a in accounts if a["account_id"] == 6)
    assert old_mortgage["date_opened"] is None


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


def test_build_transactions_resolves_linked_account_id_when_known():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3, 4, 5, 6},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
    )
    principal = next(t for t in transactions if t["transaction_id"] == 3000)
    assert principal["linked_account_id"] == 1


def test_build_transactions_nulls_linked_account_id_when_unknown():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3, 4, 5, 6},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
    )
    principal = next(t for t in transactions if t["transaction_id"] == 3001)
    assert principal["linked_account_id"] is None


def test_build_transactions_nulls_linked_account_id_when_absent():
    transactions = build_transactions(
        FIXTURES,
        known_account_ids={1, 2, 3},
        known_category_ids={10, 11},
        known_payee_ids={100, 101},
    )
    groceries = next(t for t in transactions if t["transaction_id"] == 1000)
    assert groceries["linked_account_id"] is None


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


def test_build_accounts_parses_loan_interest_rate_from_rate_user():
    accounts = build_accounts(FIXTURES)
    car_loan = next(a for a in accounts if a["account_id"] == 5)
    assert car_loan["loan_interest_rate"] == Decimal("0.05")


def test_build_accounts_falls_back_to_rate_calc_when_rate_user_blank():
    accounts = build_accounts(FIXTURES)
    old_mortgage = next(a for a in accounts if a["account_id"] == 6)
    assert old_mortgage["loan_interest_rate"] == Decimal("0.0475")


def test_build_accounts_parses_loan_payment_amount_as_positive():
    accounts = build_accounts(FIXTURES)
    car_loan = next(a for a in accounts if a["account_id"] == 5)
    assert car_loan["loan_payment_amount"] == Decimal("250.00")


def test_build_accounts_parses_loan_payment_count():
    accounts = build_accounts(FIXTURES)
    car_loan = next(a for a in accounts if a["account_id"] == 5)
    assert car_loan["loan_payment_count"] == 48


def test_build_accounts_nulls_loan_fields_for_non_loan_account():
    accounts = build_accounts(FIXTURES)
    checking = next(a for a in accounts if a["account_id"] == 1)
    assert checking["loan_interest_rate"] is None
    assert checking["loan_payment_amount"] is None
    assert checking["loan_payment_count"] is None
