# Loan Amortization View Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Amortization" view for loan accounts on the Accounts tab: a chart of the loan's actual historical balance since its earliest transaction plus a projected future balance running to payoff, computed from the loan's real interest rate/payment/term as imported from Money — not user-entered assumptions.

**Architecture:** Extend the DuckDB schema and ETL pipeline to import three loan-term fields (`rateUser`/`rateCalc`, `amtPI`, `iPmtMax`) that already exist in Money's raw `ACCT` table but aren't currently pulled in, mirroring the existing `interest_category_id` pattern exactly. A new pure calculation module (`ui/amortization.py`) infers real payment cadence from historical transaction dates (never Money's undocumented `frq` code) and projects a standard declining-balance amortization forward from the loan's most recent known balance. `ui/main_window.py` wires this in as a third mutually-exclusive toggle next to the existing "Value" checkbox, reusing `models.compute_account_value_history` for the actual/historical half of the chart and `charts.build_line_chart`'s existing multi-series support for the combined "Actual"/"Projected" chart.

**Tech Stack:** Python 3.13, PySide6 (Qt widgets + QtCharts), DuckDB, pytest, `decimal.Decimal` for all money/rate arithmetic (matching the rest of the codebase).

**Spec:** `docs/superpowers/specs/2026-08-24-loan-amortization-design.md`

## Global Constraints

- All money/rate values use `Decimal`, never `float`, matching the rest of the codebase.
- Interest rate is imported from `rateUser`, falling back to `rateCalc` only when `rateUser` is blank — never averaged or otherwise combined.
- Payment amount is imported from `amtPI` (principal + interest only), never `amtPayment` (which can include escrow) — stored as a positive value regardless of the raw field's sign.
- Payment frequency for the future projection is **inferred from real historical transaction dates**, never from Money's `frq` field (its encoding is unverified in this codebase).
- The Amortization checkbox is **disabled with a tooltip**, never hidden, when a loan account lacks usable interest-rate/payment data.
- `compute_future_amortization`'s safety cap defaults to 1200 periods (100 years at a monthly cadence) — if payoff isn't reached within that, or the payment doesn't cover the period's interest, it returns `None` and the UI falls back to showing the actual history alone with a status-bar message.
- `loan_payment_count` (from `iPmtMax`) is imported and stored but not consumed by any computation in this plan — reserved for future use.
- No new dependencies.
- `money.duckdb` must be rebuilt from the raw CSVs (rerun `etl/load.py`) after this ships — call this out at the end as a manual step, not something any task automates.

---

### Task 1: Schema migration — add loan-term columns (nullable, unpopulated)

**Files:**
- Modify: `etl/schema.py`
- Modify: `etl/load.py:52-58` (accounts INSERT — explicit column list, still 7 columns)
- Modify: `ui/writes.py:29-34` (`add_account` — explicit column list, still 7 columns)
- Modify: `ui/tests/conftest.py:26-131` (`conn`, `dict_conn`, `loan_conn` fixtures — explicit column list, rows unchanged)
- Modify: `ui/tests/test_data.py:41-49` (explicit column list, rows unchanged)
- Modify: `ui/tests/test_reports_tab.py:791,804,817,844,897,1082-1087` (explicit column list, rows unchanged)
- Test: `etl/tests/test_schema.py`

**Interfaces:**
- Produces: `accounts` table gains three nullable columns — `loan_interest_rate DECIMAL(9,6)`, `loan_payment_amount DECIMAL(18,4)`, `loan_payment_count INTEGER` — consumed by Task 2 (ETL population) and Task 3 (`data.get_loan_terms`).

This task only changes the schema and fixes every existing hardcoded `INSERT INTO accounts VALUES (...)` call site so the full test suite stays green with the three new columns always `NULL`. No loan data is actually populated yet — that's Task 2.

- [ ] **Step 1: Write failing schema tests**

Add to `etl/tests/test_schema.py`:

```python
def test_accounts_table_has_loan_term_columns():
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    columns = {row[1] for row in conn.execute("PRAGMA table_info('accounts')").fetchall()}
    assert {"loan_interest_rate", "loan_payment_amount", "loan_payment_count"} <= columns


def test_loan_term_columns_default_to_null():
    conn = duckdb.connect(":memory:")
    apply_schema(conn)
    conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance) "
        "VALUES (1, 'Loan', '6', FALSE, 0)"
    )
    row = conn.execute(
        "SELECT loan_interest_rate, loan_payment_amount, loan_payment_count "
        "FROM accounts WHERE account_id = 1"
    ).fetchone()
    assert row == (None, None, None)
```

- [ ] **Step 2: Run to verify both fail**

Run: `cd etl && python -m pytest tests/test_schema.py -v`
Expected: FAIL — `loan_interest_rate` etc. not in columns / no such column.

- [ ] **Step 3: Add the columns in `etl/schema.py`**

Change the `accounts` table definition from:

```python
CREATE TABLE accounts (
    account_id           BIGINT PRIMARY KEY,
    name                 VARCHAR NOT NULL,
    account_type         VARCHAR,
    is_closed            BOOLEAN NOT NULL DEFAULT FALSE,
    opening_balance      DECIMAL(18,4) NOT NULL DEFAULT 0,
    currency             VARCHAR NOT NULL DEFAULT 'USD',
    interest_category_id BIGINT REFERENCES categories(category_id)
);
```

to:

```python
CREATE TABLE accounts (
    account_id           BIGINT PRIMARY KEY,
    name                 VARCHAR NOT NULL,
    account_type         VARCHAR,
    is_closed            BOOLEAN NOT NULL DEFAULT FALSE,
    opening_balance      DECIMAL(18,4) NOT NULL DEFAULT 0,
    currency             VARCHAR NOT NULL DEFAULT 'USD',
    interest_category_id BIGINT REFERENCES categories(category_id),
    loan_interest_rate   DECIMAL(9,6),
    loan_payment_amount  DECIMAL(18,4),
    loan_payment_count   INTEGER
);
```

- [ ] **Step 4: Run to verify the new tests pass**

Run: `cd etl && python -m pytest tests/test_schema.py -v`
Expected: PASS

- [ ] **Step 5: Run the full etl suite to see what the schema change broke**

Run: `cd etl && python -m pytest -v`
Expected: FAIL in `tests/test_load.py` — `INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?)` now has too few values for the table's 10 columns.

- [ ] **Step 6: Fix `etl/load.py`'s accounts INSERT to use an explicit column list**

In `etl/load.py`, change:

```python
        conn.executemany(
            "INSERT INTO accounts VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    a["account_id"], a["name"], a["account_type"], a["is_closed"],
                    a["opening_balance"], a["currency"], a["interest_category_id"],
                )
                for a in accounts
            ],
        )
```

to:

```python
        conn.executemany(
            "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
            "currency, interest_category_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    a["account_id"], a["name"], a["account_type"], a["is_closed"],
                    a["opening_balance"], a["currency"], a["interest_category_id"],
                )
                for a in accounts
            ],
        )
```

- [ ] **Step 7: Run the full etl suite again**

Run: `cd etl && python -m pytest -v`
Expected: PASS (all etl tests green)

- [ ] **Step 8: Run the full ui suite to see what else the schema change broke**

Run: `cd ui && python -m pytest -v`
Expected: several FAILs — every hardcoded `INSERT INTO accounts VALUES (...)` in production code and test fixtures now has too few values.

- [ ] **Step 9: Fix `ui/writes.py`'s `add_account`**

Change:

```python
def add_account(conn, name, account_type, currency, opening_balance):
    """Inserts a new account row (open by default). Returns the new account_id."""
    account_id = _next_id(conn, "accounts", "account_id")
    conn.execute(
        "INSERT INTO accounts VALUES (?, ?, ?, FALSE, ?, ?, NULL)",
        [account_id, name, account_type, opening_balance, currency],
    )
    return account_id
```

to:

```python
def add_account(conn, name, account_type, currency, opening_balance):
    """Inserts a new account row (open by default). Returns the new account_id."""
    account_id = _next_id(conn, "accounts", "account_id")
    conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES (?, ?, ?, FALSE, ?, ?, NULL)",
        [account_id, name, account_type, opening_balance, currency],
    )
    return account_id
```

- [ ] **Step 10: Fix `ui/tests/conftest.py`'s three fixtures**

In the `conn` fixture, change:

```python
    connection.execute(
        "INSERT INTO accounts VALUES "
        "(1, 'Checking', 'Bank', FALSE, 100.00, 'USD', NULL), "
        "(2, 'Old Card', 'Credit', TRUE, 0.00, 'USD', NULL), "
        "(3, 'Brokerage', '5', FALSE, 0.00, 'SEK', NULL)"
    )
```

to:

```python
    connection.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES "
        "(1, 'Checking', 'Bank', FALSE, 100.00, 'USD', NULL), "
        "(2, 'Old Card', 'Credit', TRUE, 0.00, 'USD', NULL), "
        "(3, 'Brokerage', '5', FALSE, 0.00, 'SEK', NULL)"
    )
```

In the `dict_conn` fixture, change:

```python
    connection.execute(
        "INSERT INTO accounts VALUES "
        "(1, 'Checking', 'Bank', FALSE, 0.00, 'USD', NULL), "
        "(2, 'Savings', 'Bank', FALSE, 0.00, 'USD', NULL), "
        "(3, 'Brokerage A', '5', FALSE, 0.00, 'USD', NULL), "
        "(4, 'Brokerage B', '5', FALSE, 0.00, 'USD', NULL)"
    )
```

to:

```python
    connection.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES "
        "(1, 'Checking', 'Bank', FALSE, 0.00, 'USD', NULL), "
        "(2, 'Savings', 'Bank', FALSE, 0.00, 'USD', NULL), "
        "(3, 'Brokerage A', '5', FALSE, 0.00, 'USD', NULL), "
        "(4, 'Brokerage B', '5', FALSE, 0.00, 'USD', NULL)"
    )
```

In the `loan_conn` fixture, change:

```python
    connection.execute(
        "INSERT INTO accounts VALUES "
        "(1, 'Checking', '0', FALSE, 5000.00, 'USD', NULL), "
        "(2, 'Car Loan', '6', FALSE, -1000.00, 'USD', 20), "
        "(3, 'Foreign Checking', '0', FALSE, 5000.00, 'SEK', NULL), "
        "(4, 'Foreign Loan', '6', FALSE, -1000.00, 'SEK', 20)"
    )
```

to:

```python
    connection.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES "
        "(1, 'Checking', '0', FALSE, 5000.00, 'USD', NULL), "
        "(2, 'Car Loan', '6', FALSE, -1000.00, 'USD', 20), "
        "(3, 'Foreign Checking', '0', FALSE, 5000.00, 'SEK', NULL), "
        "(4, 'Foreign Loan', '6', FALSE, -1000.00, 'SEK', 20)"
    )
```

(Task 3 will further edit `loan_conn` to add real loan-term values — this step only restores the column count.)

- [ ] **Step 11: Fix `ui/tests/test_data.py`**

Change:

```python
    conn.execute(
        "INSERT INTO accounts VALUES "
        "(4, 'Roth IRA', '5', FALSE, 0.00, 'USD', NULL), "
        "(5, 'House', '3', FALSE, 500000.00, 'USD', NULL), "
        "(6, 'Mortgage', '6', FALSE, -300000.00, 'USD', NULL), "
        "(7, 'Visa', '1', FALSE, 0.00, 'USD', NULL), "
        "(8, 'Savings', '0', FALSE, 50.00, 'USD', NULL)"
    )
```

to:

```python
    conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES "
        "(4, 'Roth IRA', '5', FALSE, 0.00, 'USD', NULL), "
        "(5, 'House', '3', FALSE, 500000.00, 'USD', NULL), "
        "(6, 'Mortgage', '6', FALSE, -300000.00, 'USD', NULL), "
        "(7, 'Visa', '1', FALSE, 0.00, 'USD', NULL), "
        "(8, 'Savings', '0', FALSE, 50.00, 'USD', NULL)"
    )
```

- [ ] **Step 12: Fix `ui/tests/test_reports_tab.py`**

This exact line appears 5 times (lines 791, 804, 817, 844, 897) — replace **all** occurrences:

```python
    dict_conn.execute("INSERT INTO accounts VALUES (5, 'House', '3', FALSE, 300000.00, 'USD', NULL)")
```

with:

```python
    dict_conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES (5, 'House', '3', FALSE, 300000.00, 'USD', NULL)"
    )
```

And in `_add_asset_and_loan_accounts`, change:

```python
def _add_asset_and_loan_accounts(conn):
    conn.execute(
        "INSERT INTO accounts VALUES "
        "(5, 'House', '3', FALSE, 500000.00, 'USD', NULL), "
        "(6, 'Car Loan', '6', FALSE, -15000.00, 'USD', NULL)"
    )
```

to:

```python
def _add_asset_and_loan_accounts(conn):
    conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES "
        "(5, 'House', '3', FALSE, 500000.00, 'USD', NULL), "
        "(6, 'Car Loan', '6', FALSE, -15000.00, 'USD', NULL)"
    )
```

- [ ] **Step 13: Run the full ui suite**

Run: `cd ui && python -m pytest -v`
Expected: PASS (all ui tests green)

- [ ] **Step 14: Run both suites once more from repo root to confirm**

Run: `(cd etl && python -m pytest) && (cd ui && python -m pytest)`
Expected: PASS

- [ ] **Step 15: Commit**

```bash
git add etl/schema.py etl/load.py etl/tests/test_schema.py ui/writes.py ui/tests/conftest.py ui/tests/test_data.py ui/tests/test_reports_tab.py
git commit -m "feat: add nullable loan-term columns to accounts schema"
```

---

### Task 2: ETL — import loan terms from Money's raw ACCT fields

**Files:**
- Modify: `etl/column_map.py`
- Modify: `etl/transform.py` (`build_accounts`)
- Modify: `etl/load.py` (accounts INSERT — extend to 10 columns)
- Modify: `etl/tests/fixtures/ACCT.csv`
- Test: `etl/tests/test_transform.py`
- Test: `etl/tests/test_load.py`

**Interfaces:**
- Consumes: the `loan_interest_rate`/`loan_payment_amount`/`loan_payment_count` columns from Task 1.
- Produces: `build_accounts()`'s per-account dict gains three keys — `"loan_interest_rate"` (`Decimal` fraction, e.g. `Decimal("0.05")` for 5%, or `None`), `"loan_payment_amount"` (positive `Decimal`, or `None`), `"loan_payment_count"` (`int`, or `None`) — consumed by `load.py`'s INSERT in this same task, and by Task 3's `data.get_loan_terms` once loaded.

- [ ] **Step 1: Extend the ACCT.csv test fixture**

Replace the full contents of `etl/tests/fixtures/ACCT.csv` with:

```csv
hacct,szFull,at,fClosed,amtOpen,hcrnc,hcatInterest,rateUser,rateCalc,amtPI,iPmtMax
1,Checking,Bank,0,100.00,45,,,,,
2,Savings,Bank,0,0.00,38,,,,,
3,Old Card,Credit,1,,,,,,,
4,Brokerage,5,0,0.00,45,,,,,
5,Car Loan,6,0,-1000.00,45,10,5.0,5.0,-250.00,48
6,Old Mortgage,6,0,-2000.00,45,999,,4.75,-1200.00,360
```

Account 5 (Car Loan) has both `rateUser` and `rateCalc` populated (5.0% either way). Account 6 (Old Mortgage) has a blank `rateUser` and a populated `rateCalc` (4.75%), to exercise the fallback.

- [ ] **Step 2: Write failing transform tests**

Add to `etl/tests/test_transform.py`:

```python
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
```

- [ ] **Step 3: Run to verify they fail**

Run: `cd etl && python -m pytest tests/test_transform.py -v`
Expected: FAIL with `KeyError: 'loan_interest_rate'` (and similarly for the other two keys).

- [ ] **Step 4: Add the three fields to `etl/column_map.py`'s `ACCOUNTS` dict**

Change:

```python
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
```

to:

```python
ACCOUNTS = {
    "table": "ACCT",
    "id": "hacct",
    "name": "szFull",
    "account_type": "at",
    "is_closed": "fClosed",
    "opening_balance": "amtOpen",
    "currency": "hcrnc",
    "interest_category": "hcatInterest",
    "loan_interest_rate": "rateUser",
    "loan_interest_rate_fallback": "rateCalc",
    "loan_payment_amount": "amtPI",
    "loan_payment_count": "iPmtMax",
}
```

- [ ] **Step 5: Implement the parsing in `etl/transform.py`'s `build_accounts`**

Add this helper above `build_accounts`:

```python
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
```

In `build_accounts`, change the account dict construction from:

```python
        result.append({
            "account_id": account_id,
            "name": name,
            "account_type": row.get(ACCOUNTS["account_type"]) or None,
            "is_closed": (row.get(ACCOUNTS["is_closed"]) or "").strip() in ("1", "true", "True"),
            "opening_balance": opening_balance,
            "currency": currencies.get(currency_id, PRIMARY_CURRENCY),
            "interest_category_id": interest_category_id,
        })
```

to:

```python
        loan_payment_amount = _to_decimal(row.get(ACCOUNTS["loan_payment_amount"]))
        result.append({
            "account_id": account_id,
            "name": name,
            "account_type": row.get(ACCOUNTS["account_type"]) or None,
            "is_closed": (row.get(ACCOUNTS["is_closed"]) or "").strip() in ("1", "true", "True"),
            "opening_balance": opening_balance,
            "currency": currencies.get(currency_id, PRIMARY_CURRENCY),
            "interest_category_id": interest_category_id,
            "loan_interest_rate": _to_loan_rate(
                row.get(ACCOUNTS["loan_interest_rate"]), row.get(ACCOUNTS["loan_interest_rate_fallback"])
            ),
            "loan_payment_amount": abs(loan_payment_amount) if loan_payment_amount is not None else None,
            "loan_payment_count": _to_int(row.get(ACCOUNTS["loan_payment_count"])),
        })
```

- [ ] **Step 6: Run to verify the transform tests pass**

Run: `cd etl && python -m pytest tests/test_transform.py -v`
Expected: PASS

- [ ] **Step 7: Write a failing load round-trip test**

Add to `etl/tests/test_load.py`:

```python
def test_load_resolves_loan_terms(tmp_path):
    db_path = tmp_path / "test.duckdb"
    load(FIXTURES, db_path)
    conn = duckdb.connect(str(db_path))
    try:
        car_loan = conn.execute(
            "SELECT loan_interest_rate, loan_payment_amount, loan_payment_count "
            "FROM accounts WHERE account_id = 5"
        ).fetchone()
    finally:
        conn.close()
    assert car_loan == (Decimal("0.05"), Decimal("250.00"), 48)
```

- [ ] **Step 8: Run to verify it fails**

Run: `cd etl && python -m pytest tests/test_load.py -v`
Expected: FAIL — `KeyError: 'loan_interest_rate'` inside `load()`'s tuple-building comprehension (the INSERT hasn't been extended yet).

- [ ] **Step 9: Extend the accounts INSERT in `etl/load.py`**

Change:

```python
        conn.executemany(
            "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
            "currency, interest_category_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    a["account_id"], a["name"], a["account_type"], a["is_closed"],
                    a["opening_balance"], a["currency"], a["interest_category_id"],
                )
                for a in accounts
            ],
        )
```

to:

```python
        conn.executemany(
            "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
            "currency, interest_category_id, loan_interest_rate, loan_payment_amount, "
            "loan_payment_count) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    a["account_id"], a["name"], a["account_type"], a["is_closed"],
                    a["opening_balance"], a["currency"], a["interest_category_id"],
                    a["loan_interest_rate"], a["loan_payment_amount"], a["loan_payment_count"],
                )
                for a in accounts
            ],
        )
```

- [ ] **Step 10: Run to verify it passes**

Run: `cd etl && python -m pytest tests/test_load.py -v`
Expected: PASS

- [ ] **Step 11: Run the full etl suite**

Run: `cd etl && python -m pytest -v`
Expected: PASS

- [ ] **Step 12: Commit**

```bash
git add etl/column_map.py etl/transform.py etl/load.py etl/tests/fixtures/ACCT.csv etl/tests/test_transform.py etl/tests/test_load.py
git commit -m "feat: import loan interest rate, payment amount, and term from Money"
```

---

### Task 3: `data.get_loan_terms` and loan-term test fixture data

**Files:**
- Modify: `ui/data.py`
- Modify: `ui/tests/conftest.py:88-131` (`loan_conn` fixture — add real loan-term values and a fifth "Legacy Loan" account with no terms)
- Test: `ui/tests/test_data.py`

**Interfaces:**
- Consumes: `loan_interest_rate`/`loan_payment_amount`/`loan_payment_count` columns from Task 1/2.
- Produces: `data.get_loan_terms(conn, account_id) -> tuple | None` — `(interest_rate: Decimal | None, payment_amount: Decimal | None, payment_count: int | None)` for an existing account, or `None` if the account doesn't exist. Consumed by Task 5 (`main_window.py`).

- [ ] **Step 1: Give `loan_conn` real loan-term data**

In `ui/tests/conftest.py`, change the `loan_conn` fixture's accounts INSERT from:

```python
    connection.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id) VALUES "
        "(1, 'Checking', '0', FALSE, 5000.00, 'USD', NULL), "
        "(2, 'Car Loan', '6', FALSE, -1000.00, 'USD', 20), "
        "(3, 'Foreign Checking', '0', FALSE, 5000.00, 'SEK', NULL), "
        "(4, 'Foreign Loan', '6', FALSE, -1000.00, 'SEK', 20)"
    )
```

to:

```python
    connection.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id, loan_interest_rate, loan_payment_amount, "
        "loan_payment_count) VALUES "
        "(1, 'Checking', '0', FALSE, 5000.00, 'USD', NULL, NULL, NULL, NULL), "
        "(2, 'Car Loan', '6', FALSE, -1000.00, 'USD', 20, 0.06, 45.00, 24), "
        "(3, 'Foreign Checking', '0', FALSE, 5000.00, 'SEK', NULL, NULL, NULL, NULL), "
        "(4, 'Foreign Loan', '6', FALSE, -1000.00, 'SEK', 20, 0.04, 50.00, 24), "
        "(5, 'Legacy Loan', '6', FALSE, -500.00, 'USD', NULL, NULL, NULL, NULL)"
    )
```

(`Legacy Loan` is a loan account whose interest rate/payment weren't available in the source data — used by this task's and Task 5's "missing data" tests.)

- [ ] **Step 2: Write failing tests**

Add to `ui/tests/test_data.py` (add `get_loan_terms` to the existing `from data import (...)` block):

```python
def test_get_loan_terms_returns_stored_values(loan_conn):
    assert get_loan_terms(loan_conn, 2) == (Decimal("0.06"), Decimal("45.00"), 24)


def test_get_loan_terms_returns_nulls_for_loan_missing_terms(loan_conn):
    assert get_loan_terms(loan_conn, 5) == (None, None, None)


def test_get_loan_terms_returns_none_for_unknown_account(loan_conn):
    assert get_loan_terms(loan_conn, 999) is None
```

- [ ] **Step 3: Run to verify they fail**

Run: `cd ui && python -m pytest tests/test_data.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_loan_terms'`.

- [ ] **Step 4: Implement `get_loan_terms` in `ui/data.py`**

Add after `get_opening_balance`:

```python
def get_loan_terms(conn: duckdb.DuckDBPyConnection, account_id: int) -> tuple | None:
    """(interest_rate, payment_amount, payment_count) for a loan account,
    as imported from Money -- interest_rate is a fraction (e.g. 0.05 for
    5%), payment_amount is the positive principal+interest installment.
    Any field may individually be None if that data wasn't available in
    the source. Returns None only if the account itself doesn't exist."""
    return conn.execute(
        "SELECT loan_interest_rate, loan_payment_amount, loan_payment_count "
        "FROM accounts WHERE account_id = ?", [account_id],
    ).fetchone()
```

- [ ] **Step 5: Run to verify they pass**

Run: `cd ui && python -m pytest tests/test_data.py -v`
Expected: PASS

- [ ] **Step 6: Run the full ui suite**

Run: `cd ui && python -m pytest -v`
Expected: PASS (the `loan_conn` fixture change doesn't affect any other existing test, since they only assert on fields present before this change)

- [ ] **Step 7: Commit**

```bash
git add ui/data.py ui/tests/conftest.py ui/tests/test_data.py
git commit -m "feat: add get_loan_terms query and loan-term test fixture data"
```

---

### Task 4: `ui/amortization.py` — payment cadence inference and future projection

**Files:**
- Create: `ui/amortization.py`
- Test: `ui/tests/test_amortization.py`

**Interfaces:**
- Produces:
  - `AmortizationInputs` dataclass: `current_balance: Decimal` (liability convention — negative means owed), `annual_rate: Decimal` (fraction), `payment_amount: Decimal` (positive), `payments_per_year: int`, `start_date: date`.
  - `AmortizationPoint` NamedTuple: `point_date: date`, `balance: Decimal`.
  - `infer_payments_per_year(dates: list[date]) -> int`.
  - `compute_future_amortization(inputs: AmortizationInputs, max_periods: int = 1200) -> list[AmortizationPoint] | None`.
  - Consumed by Task 5 (`main_window.py`).

This module is pure (no Qt, no DB) and fully unit-testable on its own.

- [ ] **Step 1: Write failing tests for `infer_payments_per_year`**

Create `ui/tests/test_amortization.py`:

```python
from datetime import date
from decimal import Decimal

from amortization import (
    AmortizationInputs,
    compute_future_amortization,
    infer_payments_per_year,
)


def test_infer_payments_per_year_detects_monthly_cadence():
    dates = [date(2024, 1, 15), date(2024, 2, 15), date(2024, 3, 15), date(2024, 4, 15)]
    assert infer_payments_per_year(dates) == 12


def test_infer_payments_per_year_detects_quarterly_cadence():
    dates = [date(2024, 1, 1), date(2024, 4, 2), date(2024, 7, 1), date(2024, 10, 1)]
    assert infer_payments_per_year(dates) == 4


def test_infer_payments_per_year_detects_annual_cadence():
    dates = [date(2020, 1, 1), date(2021, 1, 1), date(2022, 1, 1)]
    assert infer_payments_per_year(dates) == 1


def test_infer_payments_per_year_defaults_to_monthly_with_fewer_than_two_dates():
    assert infer_payments_per_year([]) == 12
    assert infer_payments_per_year([date(2024, 1, 1)]) == 12
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd ui && python -m pytest tests/test_amortization.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'amortization'`.

- [ ] **Step 3: Implement `infer_payments_per_year` in `ui/amortization.py`**

```python
"""Loan amortization: infers real payment cadence from a loan's own
transaction history (never Money's undocumented `frq` field) and
projects a standard declining-balance schedule forward from the most
recent known balance to payoff.
"""

import calendar
import statistics
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import NamedTuple, Optional

_FREQUENCY_CANDIDATES = [(12, 30.44), (4, 91.31), (2, 182.63), (1, 365.25)]


def infer_payments_per_year(dates: list[date]) -> int:
    """Snaps the median gap between sorted dates to the nearest of
    {12, 4, 2, 1} (monthly/quarterly/semi-annual/annual) payments per
    year. Defaults to 12 (monthly) with fewer than two dates -- matches
    the overwhelming majority of real loan accounts and is a safe
    default for a loan with no payment history yet."""
    ordered = sorted(dates)
    if len(ordered) < 2:
        return 12
    gaps = [(later - earlier).days for earlier, later in zip(ordered, ordered[1:])]
    median_gap = statistics.median(gaps)
    return min(_FREQUENCY_CANDIDATES, key=lambda candidate: abs(median_gap - candidate[1]))[0]
```

- [ ] **Step 4: Run to verify they pass**

Run: `cd ui && python -m pytest tests/test_amortization.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Write failing tests for `compute_future_amortization`**

Add to `ui/tests/test_amortization.py`:

```python
def test_compute_future_amortization_projects_to_payoff():
    inputs = AmortizationInputs(
        current_balance=Decimal("-1000"),
        annual_rate=Decimal("0.10"),
        payment_amount=Decimal("600"),
        payments_per_year=1,
        start_date=date(2024, 1, 1),
    )
    points = compute_future_amortization(inputs)
    assert points == [
        (date(2025, 1, 1), Decimal("-500")),
        (date(2026, 1, 1), Decimal("0")),
    ]


def test_compute_future_amortization_returns_none_when_payment_does_not_cover_interest():
    inputs = AmortizationInputs(
        current_balance=Decimal("-1000"),
        annual_rate=Decimal("0.24"),
        payment_amount=Decimal("10"),
        payments_per_year=12,
        start_date=date(2024, 1, 1),
    )
    assert compute_future_amortization(inputs) is None


def test_compute_future_amortization_returns_none_when_max_periods_exceeded():
    inputs = AmortizationInputs(
        current_balance=Decimal("-100000"),
        annual_rate=Decimal("0.12"),
        payment_amount=Decimal("1001"),
        payments_per_year=12,
        start_date=date(2024, 1, 1),
    )
    assert compute_future_amortization(inputs, max_periods=5) is None


def test_compute_future_amortization_returns_empty_list_when_already_paid_off():
    inputs = AmortizationInputs(
        current_balance=Decimal("0"),
        annual_rate=Decimal("0.05"),
        payment_amount=Decimal("100"),
        payments_per_year=12,
        start_date=date(2024, 1, 1),
    )
    assert compute_future_amortization(inputs) == []
```

- [ ] **Step 6: Run to verify they fail**

Run: `cd ui && python -m pytest tests/test_amortization.py -v`
Expected: FAIL — `ImportError: cannot import name 'AmortizationInputs'` / `compute_future_amortization`.

- [ ] **Step 7: Implement `AmortizationInputs`, `AmortizationPoint`, and `compute_future_amortization`**

Append to `ui/amortization.py`:

```python
def _add_months(base_date: date, months: int) -> date:
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return base_date.replace(year=year, month=month, day=day)


@dataclass
class AmortizationInputs:
    current_balance: Decimal  # liability convention: negative = owed
    annual_rate: Decimal      # fraction, e.g. Decimal("0.05") for 5%
    payment_amount: Decimal   # positive, principal + interest only
    payments_per_year: int
    start_date: date          # date of current_balance


class AmortizationPoint(NamedTuple):
    point_date: date
    balance: Decimal


def compute_future_amortization(
    inputs: AmortizationInputs, max_periods: int = 1200
) -> Optional[list[AmortizationPoint]]:
    """Standard declining-balance amortization, one point per period,
    stepping forward from inputs.start_date. Each period: interest =
    -balance * (annual_rate / payments_per_year); principal_paid =
    payment_amount - interest; balance += principal_paid. The final
    balance is clamped to exactly 0. Returns [] immediately if the loan
    is already paid off (current_balance >= 0). Returns None if
    principal_paid is never positive (the payment doesn't cover the
    period's interest) or payoff isn't reached within max_periods -- the
    loan doesn't amortize under its recorded terms.

    Dates step by 12 // payments_per_year calendar months, so monthly,
    quarterly, semi-annual, and annual periods all land on sensible
    calendar dates (same day-of-month clamping as models.py's
    _add_months, duplicated here to keep this module dependency-free).
    """
    if inputs.current_balance >= 0:
        return []

    periodic_rate = inputs.annual_rate / inputs.payments_per_year
    months_per_period = 12 // inputs.payments_per_year
    balance = inputs.current_balance
    point_date = inputs.start_date
    points = []

    for _ in range(max_periods):
        interest = -balance * periodic_rate
        principal_paid = inputs.payment_amount - interest
        if principal_paid <= 0:
            return None
        point_date = _add_months(point_date, months_per_period)
        balance += principal_paid
        if balance >= 0:
            points.append(AmortizationPoint(point_date, Decimal("0")))
            return points
        points.append(AmortizationPoint(point_date, balance))

    return None
```

- [ ] **Step 8: Run to verify they pass**

Run: `cd ui && python -m pytest tests/test_amortization.py -v`
Expected: PASS (8 tests)

- [ ] **Step 9: Commit**

```bash
git add ui/amortization.py ui/tests/test_amortization.py
git commit -m "feat: add loan amortization projection engine"
```

---

### Task 5: Wire the Amortization view into `main_window.py`

**Files:**
- Modify: `ui/main_window.py`
- Test: `ui/tests/test_main_window.py`

**Interfaces:**
- Consumes: `data.get_loan_terms` (Task 3), `amortization.AmortizationInputs`/`compute_future_amortization`/`infer_payments_per_year` (Task 4), `models.compute_account_value_history` and `charts.build_line_chart` (existing).

- [ ] **Step 1: Write failing tests**

Add to `ui/tests/test_main_window.py`:

```python
def test_amortization_checkbox_disabled_for_non_loan_account(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Checking"
    )
    window.account_view.selectRow(row)
    assert not window.amortization_checkbox.isEnabled()


def test_amortization_checkbox_enabled_for_loan_with_terms(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(row)
    assert window.amortization_checkbox.isEnabled()


def test_amortization_checkbox_disabled_with_tooltip_for_loan_missing_terms(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Legacy Loan"
    )
    window.account_view.selectRow(row)
    assert not window.amortization_checkbox.isEnabled()
    assert "No interest rate/payment data" in window.amortization_checkbox.toolTip()


def test_amortization_checkbox_checked_shows_amortization_page(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(row)

    window.amortization_checkbox.setChecked(True)

    assert window.content_stack.currentWidget() is window.amortization_chart_view


def test_amortization_checkbox_unchecked_shows_transaction_table(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(row)
    window.amortization_checkbox.setChecked(True)

    window.amortization_checkbox.setChecked(False)

    assert window.content_stack.currentWidget() is window.transaction_view


def test_checking_amortization_unchecks_value_checkbox(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(row)
    window.value_checkbox.setChecked(True)

    window.amortization_checkbox.setChecked(True)

    assert not window.value_checkbox.isChecked()
    assert window.content_stack.currentWidget() is window.amortization_chart_view


def test_checking_value_unchecks_amortization_checkbox(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(row)
    window.amortization_checkbox.setChecked(True)

    window.value_checkbox.setChecked(True)

    assert not window.amortization_checkbox.isChecked()
    assert window.content_stack.currentWidget() is window.value_chart_view


def test_selecting_new_account_resets_amortization_checkbox(qapp, loan_conn):
    window = MainWindow(loan_conn)
    car_loan_row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(car_loan_row)
    window.amortization_checkbox.setChecked(True)

    checking_row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Checking"
    )
    window.account_view.selectRow(checking_row)

    assert not window.amortization_checkbox.isChecked()
    assert window.content_stack.currentWidget() is window.transaction_view


def test_amortization_chart_shows_actual_and_projected_series_for_amortizing_loan(qapp, loan_conn):
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Car Loan"
    )
    window.account_view.selectRow(row)

    window.amortization_checkbox.setChecked(True)

    series_names = {s.name() for s in window.amortization_chart_view.chart().series() if s.name()}
    assert series_names == {"Actual", "Projected"}


def test_amortization_view_shows_status_message_when_loan_does_not_amortize(qapp, loan_conn):
    loan_conn.execute(
        "INSERT INTO accounts (account_id, name, account_type, is_closed, opening_balance, "
        "currency, interest_category_id, loan_interest_rate, loan_payment_amount, "
        "loan_payment_count) VALUES "
        "(6, 'Bad Loan', '6', FALSE, -100000.00, 'USD', NULL, 0.24, 10.00, 360)"
    )
    window = MainWindow(loan_conn)
    row = next(
        r for r in range(window.account_model.rowCount())
        if window.account_model.account_at(r)[1] == "Bad Loan"
    )
    window.account_view.selectRow(row)

    window.amortization_checkbox.setChecked(True)

    assert window.content_stack.currentWidget() is window.amortization_chart_view
    assert "doesn't cover its interest" in window.statusBar().currentMessage()
    series_names = {s.name() for s in window.amortization_chart_view.chart().series() if s.name()}
    assert series_names == {"Actual"}
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd ui && python -m pytest tests/test_main_window.py -v -k amortization`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute 'amortization_checkbox'`.

- [ ] **Step 3: Add imports and the `AMORTIZATION_PAGE` constant**

In `ui/main_window.py`, change:

```python
from decimal import Decimal
from functools import partial
```

to:

```python
from datetime import date
from decimal import Decimal
from functools import partial
```

Change:

```python
import data
import theme
import writes
```

to:

```python
import data
import theme
import writes
from amortization import AmortizationInputs, compute_future_amortization, infer_payments_per_year
```

Change:

```python
TRANSACTIONS_PAGE = 0
VALUE_PAGE = 1
```

to:

```python
TRANSACTIONS_PAGE = 0
VALUE_PAGE = 1
AMORTIZATION_PAGE = 2
```

- [ ] **Step 4: Add the chart view, checkbox, and page**

Change:

```python
        self.value_chart_view = QChartView()
        self.value_chart_view.setRenderHint(QPainter.Antialiasing)
```

to:

```python
        self.value_chart_view = QChartView()
        self.value_chart_view.setRenderHint(QPainter.Antialiasing)

        self.amortization_chart_view = QChartView()
        self.amortization_chart_view.setRenderHint(QPainter.Antialiasing)
```

Change:

```python
        self.value_checkbox = QCheckBox("Value")
        self.value_checkbox.toggled.connect(self._on_value_checkbox_toggled)

        header_row = QHBoxLayout()
        header_row.addWidget(self.account_details_label, 1)
        header_row.addWidget(self.add_record_button)
        header_row.addWidget(self.account_details_button)
        header_row.addWidget(self.value_checkbox)

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.transaction_view)
        self.content_stack.addWidget(self.value_chart_view)
```

to:

```python
        self.value_checkbox = QCheckBox("Value")
        self.value_checkbox.toggled.connect(self._on_value_checkbox_toggled)

        self.amortization_checkbox = QCheckBox("Amortization")
        self.amortization_checkbox.toggled.connect(self._on_amortization_checkbox_toggled)

        header_row = QHBoxLayout()
        header_row.addWidget(self.account_details_label, 1)
        header_row.addWidget(self.add_record_button)
        header_row.addWidget(self.account_details_button)
        header_row.addWidget(self.value_checkbox)
        header_row.addWidget(self.amortization_checkbox)

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.transaction_view)
        self.content_stack.addWidget(self.value_chart_view)
        self.content_stack.addWidget(self.amortization_chart_view)
```

- [ ] **Step 5: Reset and gate the checkbox in `_on_account_selected`**

Change:

```python
    def _on_account_selected(self, selected=None, deselected=None):
        self._maybe_record_view_change()
        indexes = self.account_view.selectionModel().selectedRows()
        has_selection = bool(indexes)
        self.add_record_button.setEnabled(has_selection)
        self.account_details_button.setEnabled(has_selection)
        self.value_checkbox.setEnabled(has_selection)
        self.value_checkbox.setChecked(False)
        self.content_stack.setCurrentIndex(TRANSACTIONS_PAGE)
        if not indexes:
            self.account_details_label.setText("")
            self.transaction_model.set_transactions([])
            return
        account_id, name, account_type, currency, balance, _ = self.account_model.account_at(
            indexes[0].row()
        )
        is_investment = account_type == INVESTMENT_ACCOUNT_TYPE
        is_loan = account_type == LOAN_ACCOUNT_TYPE
        balance_label = "Value" if is_investment else "Balance"
        usd_balance = self.account_model.to_usd(currency, balance)
        try:
            transactions = data.list_transactions(self._conn, account_id)
            if is_loan:
                interest_payments = data.list_loan_interest_payments(self._conn, account_id)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to load transactions: {exc}")
            return
        if is_loan:
            display_rows = build_loan_transaction_rows(transactions, interest_payments)
```

to:

```python
    def _on_account_selected(self, selected=None, deselected=None):
        self._maybe_record_view_change()
        indexes = self.account_view.selectionModel().selectedRows()
        has_selection = bool(indexes)
        self.add_record_button.setEnabled(has_selection)
        self.account_details_button.setEnabled(has_selection)
        self.value_checkbox.setEnabled(has_selection)
        self.value_checkbox.setChecked(False)
        self.amortization_checkbox.setEnabled(False)
        self.amortization_checkbox.setChecked(False)
        self.amortization_checkbox.setToolTip("")
        self.content_stack.setCurrentIndex(TRANSACTIONS_PAGE)
        if not indexes:
            self.account_details_label.setText("")
            self.transaction_model.set_transactions([])
            return
        account_id, name, account_type, currency, balance, _ = self.account_model.account_at(
            indexes[0].row()
        )
        is_investment = account_type == INVESTMENT_ACCOUNT_TYPE
        is_loan = account_type == LOAN_ACCOUNT_TYPE
        balance_label = "Value" if is_investment else "Balance"
        usd_balance = self.account_model.to_usd(currency, balance)
        try:
            transactions = data.list_transactions(self._conn, account_id)
            if is_loan:
                interest_payments = data.list_loan_interest_payments(self._conn, account_id)
                loan_terms = data.get_loan_terms(self._conn, account_id)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to load transactions: {exc}")
            return
        if is_loan:
            has_amortization = (
                loan_terms is not None
                and loan_terms[0] is not None
                and loan_terms[1] is not None
                and loan_terms[1] > 0
            )
            self.amortization_checkbox.setEnabled(has_amortization)
            if not has_amortization:
                self.amortization_checkbox.setToolTip(
                    "No interest rate/payment data available for this loan."
                )
            display_rows = build_loan_transaction_rows(transactions, interest_payments)
```

(everything after `display_rows = build_loan_transaction_rows(...)` is unchanged)

- [ ] **Step 6: Add mutual exclusion to `_on_value_checkbox_toggled`**

Change:

```python
    def _on_value_checkbox_toggled(self, checked):
        if not checked:
            self.content_stack.setCurrentIndex(TRANSACTIONS_PAGE)
            return
        indexes = self.account_view.selectionModel().selectedRows()
```

to:

```python
    def _on_value_checkbox_toggled(self, checked):
        if not checked:
            self.content_stack.setCurrentIndex(TRANSACTIONS_PAGE)
            return
        if self.amortization_checkbox.isChecked():
            self.amortization_checkbox.blockSignals(True)
            self.amortization_checkbox.setChecked(False)
            self.amortization_checkbox.blockSignals(False)
        indexes = self.account_view.selectionModel().selectedRows()
```

- [ ] **Step 7: Add `_on_amortization_checkbox_toggled`**

Add immediately after `_on_value_checkbox_toggled`'s existing body (i.e. after the `self.content_stack.setCurrentIndex(VALUE_PAGE)` line):

```python
    def _on_amortization_checkbox_toggled(self, checked):
        if not checked:
            self.content_stack.setCurrentIndex(TRANSACTIONS_PAGE)
            return
        if self.value_checkbox.isChecked():
            self.value_checkbox.blockSignals(True)
            self.value_checkbox.setChecked(False)
            self.value_checkbox.blockSignals(False)
        indexes = self.account_view.selectionModel().selectedRows()
        if not indexes:
            self.content_stack.setCurrentIndex(TRANSACTIONS_PAGE)
            return
        account_id, name, account_type, currency, _, _ = self.account_model.account_at(
            indexes[0].row()
        )
        opening_balance = data.get_opening_balance(self._conn, account_id)
        try:
            transactions = data.list_transactions(self._conn, account_id)
            loan_terms = data.get_loan_terms(self._conn, account_id)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to load amortization schedule: {exc}")
            return
        if loan_terms is None or loan_terms[0] is None or not loan_terms[1]:
            self.content_stack.setCurrentIndex(TRANSACTIONS_PAGE)
            return
        interest_rate, payment_amount, _payment_count = loan_terms

        history = compute_account_value_history(transactions, opening_balance, is_investment=False)
        usd_history = [
            (txn_date, self.account_model.to_usd(currency, value)) for txn_date, value in history
        ]
        if usd_history:
            last_date, current_balance = usd_history[-1]
        else:
            last_date = date.today()
            current_balance = self.account_model.to_usd(currency, opening_balance or Decimal("0"))

        payments_per_year = infer_payments_per_year([txn_date for txn_date, _ in usd_history])
        inputs = AmortizationInputs(
            current_balance=current_balance,
            annual_rate=interest_rate,
            payment_amount=self.account_model.to_usd(currency, payment_amount),
            payments_per_year=payments_per_year,
            start_date=last_date,
        )
        future_points = compute_future_amortization(inputs)

        if future_points is None:
            self.statusBar().showMessage(
                "This loan's payment doesn't cover its interest — no projected payoff is possible."
            )
            chart = build_line_chart(
                f"{name} — Amortization (USD)", [("Actual", usd_history)], mark_zero=True
            )
        else:
            projected = [(last_date, current_balance)] + [
                (point.point_date, point.balance) for point in future_points
            ]
            chart = build_line_chart(
                f"{name} — Amortization (USD)",
                [("Actual", usd_history), ("Projected", projected)],
                mark_zero=True,
            )
        self.amortization_chart_view.setChart(chart)
        self.content_stack.setCurrentIndex(AMORTIZATION_PAGE)
```

- [ ] **Step 8: Run the amortization-related tests**

Run: `cd ui && python -m pytest tests/test_main_window.py -v -k amortization`
Expected: PASS (10 tests)

- [ ] **Step 9: Run the full ui suite**

Run: `cd ui && python -m pytest -v`
Expected: PASS

- [ ] **Step 10: Run both suites from repo root**

Run: `(cd etl && python -m pytest) && (cd ui && python -m pytest)`
Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add ui/main_window.py ui/tests/test_main_window.py
git commit -m "feat: add Amortization view toggle for loan accounts"
```

---

## After implementation

Rebuild `money.duckdb` from the existing raw CSVs so the new loan-term columns are actually populated for the real data:

```bash
cd etl && python load.py <path-to-raw-dir> <path-to-money.duckdb>
```

Then launch the app (`./run-ui.sh`), select a real loan account, and toggle "Amortization" to confirm the chart shows a declining balance curve to zero with a visible join point between the "Actual" and "Projected" series.
