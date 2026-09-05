# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Start with README.md

`README.md` is the primary source of truth for this project: what it does, the
two-stage extract→load pipeline, password handling, the DuckDB schema
caveats, and — in detail — every feature of the desktop UI (accounts,
investment value/activity-code semantics, RSU grants/vesting, dictionaries,
payee-merge, foreign currency handling, college tuition/projection reports,
etc.). Read it before making changes; do not duplicate its content here, and
update it when behavior it documents changes.

## Commands

Extraction + load pipeline (Java → CSV → DuckDB):

    ./extract-data-to-db.sh "My Money.mny"

(README calls this `run.sh`; the actual script in this repo is
`extract-data-to-db.sh` — use that name.)

Re-run just the load stage (e.g. after editing `etl/column_map.py`), without
redoing the Java extraction:

    .venv/bin/python etl/load.py data/raw money.duckdb

Launch the desktop UI (builds `.venv` and installs deps if needed):

    ./run-ui.sh

Tests:

    cd extract-mny && mvn test && cd ..                        # Java extractor
    .venv/bin/pip install -r etl/requirements-dev.txt
    .venv/bin/pytest etl/tests                                  # ETL
    .venv/bin/pip install -r ui/requirements.txt
    .venv/bin/pytest ui/tests                                   # UI

Run a single test file/case (pytest, applies to both `etl/tests` and `ui/tests`):

    .venv/bin/pytest ui/tests/test_models.py
    .venv/bin/pytest ui/tests/test_models.py::test_name -v

## Architecture

Three independent stages, each with its own toolchain and its own tests:

1. **`extract-mny/`** — Java/Maven. Opens the `.mny` file directly (MSISAM-
   encrypted Jet/Access DB) via Jackcess/Jackcess Encrypt and dumps every
   internal table verbatim to `data/raw/<TABLE>.csv` + `data/raw/manifest.csv`.
   Knows nothing about the target schema — pure extraction.
2. **`etl/`** — Python. `column_map.py` maps Money's undocumented internal
   table/column names to the clean schema (`schema.py`); `transform.py` does
   type/value conversion (see `moneytypes.py` for `MONEY_SCALE` etc.);
   `load.py` orchestrates reading `data/raw/*.csv` and loading `money.duckdb`.
   This is the layer to edit when `data/raw/manifest.csv` doesn't match
   `column_map.py` for a given Money file (see README's mapping caveat).
3. **`ui/`** — PySide6 desktop app, read-mostly against `money.duckdb`:
   - `data.py` is the **only** read/query layer (raw SQL over the DuckDB
     connection) — it is explicitly read-only, enforced by convention, not by
     a separate DB user/permissions.
   - `writes.py` is the **only** write layer — every mutating path in the UI
     (add record, add grant, add account, dictionary inserts, payee-alias
     edits) funnels through here, each insert wrapped in one explicit
     transaction. Adding a new UI feature that mutates data should add a
     function here rather than issuing SQL from a dialog/widget directly.
   - `models.py` holds the Qt model classes (`QAbstractTableModel` /
     `QAbstractListModel`) that adapt `data.py` query results for the table
     views; this is also where cross-cutting interpretation of Money's raw
     activity codes into share-count/valuation logic lives (mirrors the
     activity-code semantics documented in README).
   - `main_window.py` wires up the tabs/widgets; most individual dialogs and
     tabs (`*_dialog.py`, `*_tab.py`) are single-purpose and named for the
     feature they implement (grants, QFX import, payee merge, projection
     reports, college tuition, etc. — see README for what each does).
   - Config/state the UI persists between runs (exchange rate, projection
     settings, RSU tax settings, college tuition settings, payee aliases)
     lives in `config/*.json`, not in `money.duckdb`.
   - `money.duckdb` is rebuilt from scratch by the extract/load pipeline, so
     anything the UI writes into it does not survive a re-extraction; this is
     why `payee_aliases.json` (payee-merge decisions) is kept as a sibling
     file instead of a DB table.

Neither `.mny`/`.mbf` source files nor generated output (`data/raw/`,
`money.duckdb`) are committed — see `.gitignore`; they contain personal
financial data.
