"""Mapping from Money's raw internal table/column names to normalized
fields.

These names come from prior community reverse-engineering of the Money
file format (not official documentation) and are the best known guesses
as of writing. THE FIRST TIME this runs against a real .mny export,
compare these against data/raw/manifest.csv (which lists every real
table, column, and jackcess-reported column type) and correct any
mismatches here before trusting the output. See README.md.
"""

ACCOUNTS = {
    "table": "ACCT",
    "id": "hacct",
    "name": "szFull",
    "account_type": "at",
    "is_closed": "fClosed",
    "opening_balance": "amtOpen",
    "currency": "hcrnc",
    "interest_category": "hcatInterest",
}

# Currency reference table. ACCOUNTS["currency"] holds a foreign key (hcrnc)
# into this table; szIsoCode is the 3-letter code (e.g. "USD", "SEK").
CURRENCIES = {
    "table": "CRNC",
    "id": "hcrnc",
    "iso_code": "szIsoCode",
}

CATEGORIES = {
    "table": "CAT",
    "id": "hcat",
    "name": "szFull",
}

PAYEES = {
    "table": "PAY",
    "id": "hpay",
    "name": "szFull",
}

SECURITIES = {
    "table": "SEC",
    "id": "hsec",
    "name": "szFull",
}

TRANSACTIONS = {
    "table": "TRN",
    "id": "htrn",
    "account_id": "hacct",
    "category_id": "hcat",
    "payee_id": "lHpay",
    "date": "dt",
    "amount": "amt",
    "memo": "mMemo",
    "security_id": "hsec",
    "activity": "act",
    "linked_account_id": "hacctLink",
}

# Investment detail for a transaction (quantity/unit price of a buy, sell,
# etc.). One row per investment transaction_id, joined via TRN_INV.htrn.
TRANSACTION_INVESTMENTS = {
    "table": "TRN_INV",
    "id": "htrn",
    "quantity": "qty",
    "price": "dPrice",
}
