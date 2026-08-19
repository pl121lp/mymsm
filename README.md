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

### Diagnosing "Incorrect password" errors

If the extractor rejects a password you're sure is correct, run the standalone
diagnostic tool instead of the full pipeline:

    tools/mny-password-diag.sh "My Money.mny"
    MNY_PASSWORD='your-password' tools/mny-password-diag.sh "My Money.mny"

It resolves the password the same way `run.sh` does, then prints it back
verbatim (bracketed as `[...]` so stray leading/trailing whitespace is
visible) along with its length and a non-reversible fingerprint, right before
feeding it to the decryption step — so you can see exactly what Java received
versus what you meant to type. It then tries to open the file and reports
whether the password was accepted. Because it prints the password to your
terminal, don't run it where the output could be captured or shared (screen
recordings, shared terminals, CI logs). A mismatch between what's printed and
what you intended usually means shell quoting or a typo changed the password
before it ever reached the decryption step (a common cause: an unquoted
`MNY_PASSWORD` containing `$`, `` ` ``, `!`, or spaces gets mangled by the
shell). It also tells you if the file isn't a valid Money database at all
(e.g. you pointed it at a `.mbf` backup instead of the `.mny` file — those
are a different format).

Case doesn't matter for Money passwords — the underlying encryption already
normalizes to uppercase before comparing — so that's never the cause.

If you don't have the password at all, Microsoft Money itself can save a copy
of the file without password protection (open it in Money, then File > Save
As with the password field cleared) — simpler than trying to recover it here.

`tools/` is meant for standalone maintenance/diagnostic utilities like these,
separate from the two-stage extraction pipeline; feel free to extend
`PasswordDiag` (`extract-mny/src/main/java/com/mymsm/extract/`) with more
checks as new issues come up.

## Querying the result

    .venv/bin/python -c "
    import duckdb
    conn = duckdb.connect('money.duckdb')
    print(conn.execute('SELECT * FROM accounts').fetchdf())
    "

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
