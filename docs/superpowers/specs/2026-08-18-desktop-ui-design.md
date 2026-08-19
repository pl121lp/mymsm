# Desktop UI for Browsing Extracted Money Data — Design

Date: 2026-08-18
Status: Approved for implementation

## Problem

The extraction pipeline (see `2026-08-15-money-extraction-design.md`) now
produces `money.duckdb` with accounts, transactions, categories, and payees.
The user wants a way to browse that data — see the list of accounts and
drill into an account's transactions — without writing ad-hoc SQL each time.
Adding/editing records is a future goal, explicitly out of scope here.

## Constraints & context

- Dataset is small: 142 accounts, ~49k transactions, ~15k payees, 231
  categories. Every query DuckDB will run against this returns in
  single-digit milliseconds — performance is not a design constraint, and
  no caching or background-thread query execution is needed.
- This is a personal, local-only tool — no deployment, no multi-user
  concerns, no auth.
- User requirements confirmed during brainstorming:
  - Desktop app using PySide6 (Qt6 bindings, LGPL — no licensing concerns).
  - Flow: account list on the left, selecting an account shows its
    transactions on the right (not a single unified transaction table).
  - Closed accounts hidden by default, with a toggle to show them.
  - Read-only for this iteration; the design should not preclude adding
    write/edit support later, but no editing UI is built now.

## Architecture

A new `ui/` package, sibling to `etl/` and `extract-mny/`, separating data
access from widgets:

```
ui/
  main.py          entry point: opens the DuckDB connection, builds
                    QApplication + MainWindow, shows it
  data.py          DuckDB query layer: list_accounts(include_closed),
                    list_transactions(account_id)
  models.py        QAbstractTableModel subclasses that adapt data.py's
                    query results for the two QTableViews
  main_window.py   QMainWindow: account list pane + transaction table pane,
                    wires selection changes to queries
  requirements.txt PySide6
```

`data.py` functions take an open connection and return plain Python data
(lists of tuples/dicts) — no Qt types — so they're usable and testable
independently of the GUI. This mirrors the existing `etl/` split between
data logic and I/O, and keeps a clean seam for adding write functions
(e.g. `update_transaction(...)`) later without restructuring.

Rejected alternatives:
- **Single-file script** — faster to start, but mixes query logic and
  widget code in a way that gets harder to extend once editing is added.
- **Threaded/async query execution** — unnecessary given query latency is
  imperceptible at this data size; would add complexity (signals across
  threads, cancellation) with no user-visible benefit.

## Data flow

1. `main.py` resolves the path to `money.duckdb` (project root, same
   convention as `run.sh`), opens it **read-only**, and passes the
   connection into `MainWindow`.
2. On startup, `MainWindow` calls `data.list_accounts(include_closed=False)`
   and populates the left-hand `QTableView` (columns: name, account_type).
   A checkbox above the list toggles `include_closed` and re-queries.
3. Selecting a row in the account list triggers
   `data.list_transactions(account_id)`, which joins in category and payee
   names and returns rows sorted by `txn_date` descending. This populates
   the right-hand `QTableView` (columns: date, payee, category, memo,
   amount).
4. No write operations, no manual refresh needed beyond re-selecting —
   every interaction is a fresh, cheap query.

## Error handling

- If `money.duckdb` does not exist at the path `main.py` expects, show a
  `QMessageBox` telling the user to run `./run.sh "<file.mny>"` first, then
  exit cleanly (no traceback).
- If a query in `data.py` raises (e.g. unexpected schema drift), catch it
  at the call site in `main_window.py` and show the error in the status
  bar rather than crashing the window.

## Testing & packaging

- `data.py`'s functions are tested with `pytest` against a small fixture
  DuckDB file (created in a test fixture, same pattern as `etl/tests`) —
  covering `list_accounts` with/without closed accounts, and
  `list_transactions` joins/sorting.
- Widget code (`main_window.py`, `models.py`) is not covered by automated
  tests, consistent with typical GUI code — verified by running the app.
- New `ui/requirements.txt` (`PySide6`) installed into the existing
  project-local `.venv` (same `.venv` the ETL stage uses).
- New `run-ui.sh` launcher at the project root, mirroring `run.sh`'s style,
  that ensures `.venv` has UI dependencies installed and then runs
  `ui/main.py`.

## Out of scope (this iteration)

- Adding, editing, or deleting accounts/transactions.
- Filtering/searching within the transaction table.
- Any packaging beyond a local launcher script (no installer, no
  cross-platform distribution).
