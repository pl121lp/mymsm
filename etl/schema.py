"""DuckDB schema for the extracted Money data."""

import duckdb

SCHEMA_SQL = """
CREATE TABLE accounts (
    account_id       BIGINT PRIMARY KEY,
    name             VARCHAR NOT NULL,
    account_type     VARCHAR,
    is_closed        BOOLEAN NOT NULL DEFAULT FALSE,
    opening_balance  DECIMAL(18,4) NOT NULL DEFAULT 0,
    currency         VARCHAR NOT NULL DEFAULT 'USD'
);

CREATE TABLE categories (
    category_id   BIGINT PRIMARY KEY,
    name          VARCHAR NOT NULL
);

CREATE TABLE payees (
    payee_id      BIGINT PRIMARY KEY,
    name          VARCHAR NOT NULL
);

CREATE TABLE securities (
    security_id   BIGINT PRIMARY KEY,
    name          VARCHAR NOT NULL
);

CREATE TABLE transactions (
    transaction_id  BIGINT PRIMARY KEY,
    account_id      BIGINT NOT NULL REFERENCES accounts(account_id),
    category_id     BIGINT REFERENCES categories(category_id),
    payee_id        BIGINT REFERENCES payees(payee_id),
    txn_date        DATE NOT NULL,
    amount          DECIMAL(18,4) NOT NULL,
    memo            VARCHAR,
    security_id     BIGINT REFERENCES securities(security_id),
    activity        VARCHAR,
    quantity        DECIMAL(18,4),
    price           DECIMAL(18,6)
);

CREATE INDEX idx_transactions_date ON transactions(txn_date);
CREATE INDEX idx_transactions_account ON transactions(account_id);
CREATE INDEX idx_transactions_category ON transactions(category_id);
"""


def apply_schema(conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute(SCHEMA_SQL)
