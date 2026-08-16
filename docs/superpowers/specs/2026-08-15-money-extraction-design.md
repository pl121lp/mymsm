# Microsoft Money (.mny) Extraction to DuckDB — Design

Date: 2026-08-15
Status: Approved for implementation

## Problem

The user has a Microsoft Money data file (`My Money.mny`, ~64MB) and no working
Microsoft Money installation. They want their account data (accounts,
transactions, categories, payees) extracted out of the proprietary,
encrypted `.mny` format and loaded into an open-source database with fast
retrieval characteristics, so the data can be queried/analyzed without
depending on Money ever again.

## Constraints & context

- `.mny` files are an MSISAM-encrypted variant of the Jet/Access database
  format. There is no mature pure-Python library that can open them.
- `jackcess` + `jackcess-encrypt` (Apache-licensed, Maven Central) are a
  mature, actively-referenced Java library pair that implement the MSISAM
  decryption codec specifically to support reading Microsoft Money files.
  This is the same underlying mechanism the (GUI-only, unmaintained)
  Sunriise tool uses — we use the libraries directly instead of that GUI,
  so the whole pipeline is scriptable with no manual steps.
- Money's internal table/column names are not officially documented and are
  known only through prior reverse-engineering efforts (table names like
  `ACCT`, `TRN`, `CAT`, `PAY`). Exact column layouts can drift slightly
  across Money versions/years, so the transform stage must be defensive and
  its output must be checked against the real file on first run.
- User requirements confirmed during brainstorming:
  - One-time Java dependency is acceptable, but the whole pipeline must be
    scriptable/reproducible (rerunnable without manual GUI steps).
  - Python dependencies must be isolated in a project-local `.venv`.
  - Target database: DuckDB (chosen for fast analytical/aggregate queries
    typical of personal finance analysis, embedded/single-file, first-class
    Python + SQL support).
  - Data scope: accounts, transactions, categories, payees (not
    investments/securities).
  - Git repo should be initialized for this project.
  - A README documenting all dependencies and run steps is required.

## Architecture

Three independently-rerunnable stages:

1. **Extract** (Java, Maven project `extract-mny/`) — opens the `.mny` file
   directly via `jackcess`/`jackcess-encrypt` and dumps every internal table
   verbatim to `data/raw/<TABLE>.csv`, plus a `manifest.csv` of row counts
   per table. Dumping *everything* (not just the tables we think we need)
   means the fragile, undocumented-schema exploration/debugging happens in
   Python against static CSVs, without re-running the Java/decryption step.
2. **Transform + Load** (Python, `etl/`, run inside `.venv`) — reads the raw
   CSVs, identifies the tables/columns for accounts, transactions,
   categories, and payees, resolves foreign keys (category id → name,
   payee id → name, account id → name), converts Money's fixed-point
   currency and date encodings to normal types, and writes normalized
   tables into `money.duckdb` with indexes for fast retrieval.
3. **Output** — `money.duckdb`, a single-file DuckDB database with tables:
   `accounts`, `categories`, `payees`, `transactions` (foreign-keyed to the
   first three), indexed on transaction date/account/category.

```
mymsm/
├── extract-mny/                # Java/Maven: .mny -> raw CSVs
│   ├── pom.xml
│   └── src/main/java/com/mymsm/extract/Main.java
├── etl/                        # Python: raw CSVs -> DuckDB
│   ├── requirements.txt
│   ├── schema.py                # DuckDB table DDL
│   ├── transform.py             # raw CSV -> normalized rows
│   └── load.py                  # entry point
├── data/raw/                    # raw per-table CSV dump (gitignored)
├── money.duckdb                 # final output (gitignored)
├── run.sh                       # one-command pipeline: .mny -> money.duckdb
├── README.md                    # dependencies + run instructions
└── .gitignore
```

`.gitignore` excludes `*.mny`, `*.mbf`, `data/raw/`, and `money.duckdb` —
the source file and every derived artifact contain sensitive personal
financial data and must never be committed, even to this local repo.

## Component detail

### `extract-mny` (Java)

- `pom.xml` pins exact versions of `com.healthmarketscience.jackcess:jackcess`
  and `com.healthmarketscience.jackcess:jackcess-encrypt`, built as a
  single executable jar (`maven-shade-plugin` or `assembly` plugin) so it
  can be run with a plain `java -jar`.
- `Main.java` takes `<input.mny> <output_dir>` as arguments, opens the
  database read-only with a `CryptCodecProvider` supplied, iterates every
  user table, and writes each to `<output_dir>/<TABLE>.csv` using a plain
  CSV writer (no external CSV library needed for this — Money table
  contents are simple scalar columns).
- Also writes `<output_dir>/manifest.csv`: table name, row count, column
  names — this becomes the primary debugging aid for the Python stage,
  and confirms to the user (via `run.sh` output) that extraction succeeded
  before Python even runs.

### `etl` (Python, in `.venv`)

- `requirements.txt`: `duckdb` (Python bindings, which also provide the
  CLI). No `pandas` dependency — CSV parsing and transformation is simple
  enough with the stdlib `csv` module, and skipping pandas keeps the venv
  small; this can be revisited if transformation logic gets unwieldy.
- `schema.py`: DDL for the four DuckDB tables (`accounts`, `categories`,
  `payees`, `transactions`) plus indexes.
- `transform.py`: functions that read specific raw tables (`ACCT`, `CAT`,
  `PAY`, `TRN`) from `data/raw/`, and yield normalized rows. Defensive:
  rows/columns that don't match the expected shape are logged and skipped
  rather than raising, and a summary of extracted-vs-skipped counts is
  printed at the end.
- `load.py`: CLI entry point — reads `data/raw/`, creates/overwrites
  `money.duckdb`, applies schema, runs the transform, loads rows, prints a
  final summary (row counts per table) for the user to sanity-check
  against Money's own UI.

### `run.sh`

Orchestrates both stages end-to-end:
```
./run.sh "My Money.mny"
```
1. Builds the Java extractor if not already built (`mvn -q package`).
2. Runs it against the given `.mny` file, writing to `data/raw/`.
3. Activates `.venv` (creating it and installing `requirements.txt` on
   first run if missing).
4. Runs `etl/load.py` to produce `money.duckdb`.

### README.md

Documents: what the tool does, prerequisites (JDK, Maven, Python 3),
Java dependencies (jackcess, jackcess-encrypt, with links), Python
dependencies (duckdb), one-time setup steps, and the single command to
run the whole pipeline. Also documents how to open/query the resulting
`money.duckdb` (DuckDB CLI or Python).

## Error handling

- Java stage: if the file can't be opened/decrypted (wrong codec, corrupt
  file), the tool exits non-zero with the underlying jackcess exception
  message — no silent partial output.
- Python stage: per-row/column defensive skipping (see above) rather than
  hard failure, so a single unexpected value doesn't abort the whole load;
  a final summary makes silent data loss visible instead of hidden.

## Testing

- The Java and Python code will be written and reviewed for correctness,
  but there is no synthetic `.mny` file to test against automatically —
  the real integration test is running `run.sh` against the user's actual
  `My Money.mny`. Expect a follow-up iteration to adjust the column
  mapping in `transform.py` once we see real table/column names and
  values from the manifest and raw CSVs.
- Once `money.duckdb` is produced, verification is: row counts per table
  match the manifest reasonably, and a handful of spot-checked
  transactions/balances match what's visible if the user has any other
  record (e.g. recent bank statement) of their accounts.

## Out of scope

- Investment/security holdings and investment transactions.
- Budgets, scheduled/recurring transaction templates, reports.
- Any write-back to Money or ongoing sync — this is a one-time (rerunnable)
  extraction, not a live integration.
