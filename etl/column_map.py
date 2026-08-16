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

TRANSACTIONS = {
    "table": "TRN",
    "id": "htrn",
    "account_id": "hacct",
    "category_id": "hcat",
    "payee_id": "hpay",
    "date": "dt",
    "amount": "amt",
    "memo": "mem",
}
