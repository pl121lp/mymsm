# mymsm — Microsoft Money data extraction

Extracts accounts, transactions, categories, and payees out of a
Microsoft Money `.mny` file into a DuckDB database, without needing
Microsoft Money installed.

## How it works

Two stages, orchestrated by `run.sh`:

1. **`extract-mny/`** (Java) opens the `.mny` file directly — it's an
   MSISAM-encrypted Jet/Access database — using the open-source
   [Jackcess](https://jackcess.sourceforge.io/) and
   [Jackcess Encrypt](https://jackcessencrypt.sourceforge.io/) libraries,
   and dumps every internal table to `data/raw/<TABLE>.csv`, plus a
   `data/raw/manifest.csv` listing every table's row count and column
   names/types.
2. **`etl/`** (Python) reads those raw CSVs, maps Money's internal
   schema (best-effort, see caveat below) to a clean relational schema,
   and loads it into `money.duckdb`.

## Prerequisites

- JDK 17+ and Maven (for the extraction stage)
- Python 3.10+ (for the load stage)

## Dependencies

**Java** (`extract-mny/pom.xml`, resolved automatically by Maven):
- `com.healthmarketscience.jackcess:jackcess:4.0.8` — reads Jet/Access database files
- `com.healthmarketscience.jackcess:jackcess-encrypt:4.0.3` — adds the MSISAM decryption codec Money uses
- `org.junit.jupiter:junit-jupiter:5.10.2` (test only)

**Python** (`etl/requirements.txt`, installed into a project-local `.venv`):
- `duckdb` — the target database, plus its Python bindings
- `pytest` (dev only, `etl/requirements-dev.txt`) — test runner

## Running

    ./run.sh "My Money.mny"

This builds the Java extractor if needed, runs it against your file into
`data/raw/`, creates `.venv` and installs Python dependencies if needed,
and produces `money.duckdb` in the project root.

Neither the source `.mny`/`.mbf` files nor any generated output
(`data/raw/`, `money.duckdb`) are committed to git — see `.gitignore`.
They all contain your personal financial data.

## Password protection

If your `.mny` file is password-protected, you can provide the password in one of two ways:

1. **Set the `MNY_PASSWORD` environment variable** before running the script:

       MNY_PASSWORD='your-password' ./run.sh "My Money.mny"

2. **Run the script normally** — if no password is set via environment and a terminal is
   attached, the extractor will prompt you interactively:

       ./run.sh "My Money.mny"

In a non-interactive context (e.g., cron or a CI/CD pipeline) with a password-protected
file, you must use the environment variable to avoid an error.

## Querying the result

    .venv/bin/python -c "
    import duckdb
    conn = duckdb.connect('money.duckdb')
    print(conn.execute('SELECT * FROM accounts').fetchdf())
    "

## Browsing the data

    ./run-ui.sh

Opens a desktop window (PySide6) listing accounts on the left; selecting
one shows its transactions on the right. Closed accounts are hidden by
default — check "Show closed accounts" to see them. Read-only: this tool
does not modify `money.duckdb`. Requires `money.duckdb` to already exist
(run `./extract-data-to-db.sh` first if it doesn't).

## Important caveat: column mapping may need adjustment

Money's internal table/column names (`ACCT`, `TRN`, `CAT`, `PAY`, etc.)
are not officially documented — the mapping in `etl/column_map.py` is
based on prior community reverse-engineering and is a best-effort guess.
**The first time you run this against your real file**, open
`data/raw/manifest.csv` and compare it against `etl/column_map.py`: if
any table/column name doesn't match, or if `load.py`'s printed summary
shows more skipped rows than expected, update `etl/column_map.py`
(and, if currency amounts look off by a factor, `MONEY_SCALE` in
`etl/moneytypes.py`) and rerun — no need to redo the Java extraction
step, `etl/load.py` alone can be rerun directly against the existing
`data/raw/`:

    .venv/bin/python etl/load.py data/raw money.duckdb

## Running tests

    cd extract-mny && mvn test && cd ..
    .venv/bin/pip install -r etl/requirements-dev.txt
    .venv/bin/pytest etl/tests
