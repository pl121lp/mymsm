# AGENTS.md

## Project overview

`mymsm` extracts data from Microsoft Money `.mny` files into a local DuckDB
database and provides a PySide6 desktop UI for browsing and selectively adding
data. Read `README.md` before making changes: it is the source of truth for
user-facing behavior, setup, privacy expectations, data-mapping caveats, and
the supported UI features. Update it whenever a documented behavior changes.

The project has three independent stages:

1. `extract-mny/` — Java/Maven extraction. It reads the encrypted MSISAM
   Jet/Access database with Jackcess and Jackcess Encrypt, then writes every
   source table verbatim to `data/raw/<TABLE>.csv` and `data/raw/manifest.csv`.
   Keep this stage independent of the target schema.
2. `etl/` — Python load process. `column_map.py` maps Money's undocumented
   schema, `transform.py` converts values, `moneytypes.py` defines monetary
   interpretation (including `MONEY_SCALE`), `schema.py` defines the clean
   schema, and `load.py` creates `money.duckdb`.
3. `ui/` — PySide6 desktop application, read-mostly against `money.duckdb`.

## UI boundaries

- Put DuckDB reads and queries in `ui/data.py` only.
- Put every UI mutation in `ui/writes.py` only. Each write path uses an
  explicit transaction; add a function there instead of executing SQL in a
  dialog or widget.
- `ui/models.py` contains Qt models and shared interpretation of investment
  activity codes used for share counts and valuation.
- `ui/main_window.py` connects the feature tabs and dialogs. Keep individual
  dialogs/tabs focused on their named feature.
- Persist UI settings and state in `config/*.json`, not in `money.duckdb`.
  The database is rebuilt by extraction/loading, so UI-written records do not
  survive re-extraction. Payee aliases are intentionally stored beside the DB
  in `payee_aliases.json` and applied at read time.

## Data and privacy

Microsoft Money source files (`.mny`, `.mbf`) and generated data
(`data/raw/`, `money.duckdb`) contain personal financial information. They are
git-ignored and must not be committed, added as fixtures, or exposed in logs.
Use the existing synthetic test fixtures under `etl/tests/fixtures/`.

Money's internal table and column names are undocumented and the ETL mapping
is best-effort. When working with a real file, compare `data/raw/manifest.csv`
with `etl/column_map.py`; adjust the mapping (or `MONEY_SCALE` where
appropriate) and rerun the load stage without repeating extraction.

## Common commands

Run extraction and load:

```sh
./extract-data-to-db.sh "My Money.mny"
```

For password-protected files, use `MNY_PASSWORD` or run in an interactive
terminal so the extractor can prompt. Re-run only the load stage after an ETL
change:

```sh
.venv/bin/python etl/load.py data/raw money.duckdb
```

Launch the UI:

```sh
./run-ui.sh
```

Run tests relevant to a change:

```sh
cd extract-mny && mvn test && cd ..
.venv/bin/pip install -r etl/requirements-dev.txt
.venv/bin/pytest etl/tests
.venv/bin/pip install -r ui/requirements.txt
.venv/bin/pytest ui/tests
```

Run focused pytest tests with, for example:

```sh
.venv/bin/pytest ui/tests/test_models.py::test_name -v
```

## Change guidance

- Preserve the extractor → raw CSV → ETL → DuckDB separation of concerns.
- Keep `data.py` read-only and route UI writes through `writes.py`.
- Add or update focused tests in the matching component (`extract-mny`, `etl`,
  or `ui`) for behavioral changes.
- Do not rely on manual UI additions surviving an extract/load rebuild.
