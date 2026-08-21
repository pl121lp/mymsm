# Add Record to Account — Design

Date: 2026-08-20
Status: Approved for implementation

## Problem

The desktop browser (`2026-08-18-desktop-ui-design.md`,
`2026-08-19-dictionaries-ui-design.md`) is read-only: `money.duckdb` is
opened with `read_only=True`, and even the payee-merge feature deliberately
avoids writing to it (recorded in a sidecar JSON instead). There is no way
to add a transaction to an account from the UI.

This adds that capability: a per-account "Add Record" action that inserts a
new transaction, auto-creating new Category/Payee/Security dictionary
entries by name if the entered value doesn't already exist, with
autocomplete against existing dictionary values while typing.

## Constraints & context

- Confirmed during brainstorming:
  - Re-running `./extract-data-to-db.sh` fully deletes and rebuilds
    `money.duckdb` from the `.mny` file (`load.py`: `db_path.unlink()` then
    full re-insert). Manually-added records **will not survive** a
    re-extraction. This is accepted as out of scope — no changes to
    `etl/load.py`.
  - Both cash-type accounts (Checking/Savings, Credit, Asset, Loan) and
    investment accounts are in scope for v1.
  - New dictionary/transaction IDs use `MAX(id)+1` per table, continuing
    the existing positive-ID sequence (not a separate negative-ID range).
  - Entry UX is a modal dialog (`AddRecordDialog`), not inline table-row
    editing — see Architecture below for the reasoning.
- The app's read-only stance was a deliberate design choice up to now; this
  feature is an intentional, scoped exception to it, not a reversal of that
  principle elsewhere (queries in `data.py` stay read-only).

## Architecture

```
ui/
  main.py           duckdb.connect(..., read_only=True) → read_only=False.
                     Single connection, used for both reads and writes.
  writes.py         (new) add_transaction(conn, ...) plus
                     _find_or_create_category/_payee/_security(conn, name).
                     All DB mutation lives here; data.py stays query-only.
  add_record_dialog.py   (new) AddRecordDialog(QDialog) — the form.
  main_window.py    Row-action buttons gain "Add Record", opening the
                     dialog for that account; on accept, reloads the
                     transaction table (same path as _on_account_selected).
```

`writes.py` is separate from `data.py` because `data.py`'s docstring
currently states "Read-only: no writes here" and existing code (and tests)
rely on that being true; splitting keeps that contract intact rather than
weakening it.

`add_record_dialog.py` is a new file rather than inlined into
`main_window.py`, following the precedent set by `payee_merge_dialog.py`:
dialog widgets with their own field wiring and validation live in their own
module, and `main_window.py` only instantiates them.

**Entry point & UX**: "Add Record" joins the existing Details/Transactions/
Value buttons in each account row. It opens
`AddRecordDialog(conn, account_id, account_type)`, a modal `QFormLayout`
with:
- Cash accounts: Date, Payee, Category, Memo, Amount.
- Investment accounts: Date, Security, Activity (Buy/Sell), Quantity,
  Price, Amount, Memo.

A modal dialog was chosen over inline last-row table entry because (a) the
app already establishes the dialog convention for data-mutating actions via
`payee_merge_dialog.py`, (b) cash and investment accounts need different
field sets, which a dialog shows/hides based on account type far more
simply than per-column table-cell delegates would, and (c) validation and
inline error messages are natural in a form and awkward in a table cell.

Rejected alternative — inline last-row entry in `QTableView`: would need
custom `QComboBox`+`QCompleter` and `QDateEdit` cell delegates per editable
column, doubled for the cash/investment column-set difference the table
already switches on (`TransactionTableModel._columns`). More Qt machinery
for a rarer action (adding one record at a time, not bulk entry).

## Data flow

1. Dialog opens: loads `data.list_categories(conn)`, `data.list_payees(conn)`,
   `data.list_securities(conn)` (already existing query functions) to seed
   `QCompleter`s (case-insensitive, `PopupCompletion`) on the Category,
   Payee, and Security `QLineEdit`s.
2. User fills the form. Date defaults to today. OK is disabled until
   required fields are valid (see Error handling).
3. On OK, `writes.py`'s `add_transaction(conn, account_id, ...)` runs
   inside one `BEGIN ... COMMIT`:
   - For each of Payee/Category/Security that's non-empty: case-insensitive
     exact match against that dictionary's existing names. Match →
     reuse its id. No match → insert a new row (`MAX(id)+1`) and use the
     new id. This is the "new value auto-adds to the dictionary" behavior
     requested.
   - Insert the new `transactions` row with `transaction_id = MAX(id)+1`,
     the resolved category_id/payee_id/security_id (NULL where the field
     was left blank), and the entered date/amount/memo/activity/quantity/
     price.
   - On any error, `ROLLBACK` — no partial dictionary entries or orphan
     transactions.
4. On success, the dialog closes and `main_window.py` reloads that
   account's transactions the same way `_on_account_selected` already does,
   so the new row appears immediately.

## Error handling

- Required fields: Date, Amount always. Investment accounts additionally
  require Security, Activity, Quantity, and Price — the Activity field is a
  dropdown limited to Buy/Sell (the only activity codes the app understands
  well enough to affect share counts, per `models.py`'s `ACTIVITY_LABELS`
  and the README caveat), so all four are always required together, not
  conditionally. Cash-account Payee/Category/Memo stay optional, matching
  the existing nullable schema columns.
- Amount/Quantity/Price are parsed as `Decimal` (matching the schema's
  `DECIMAL` columns and existing money handling in `models.py`); invalid
  numeric input keeps OK disabled with an inline hint rather than raising
  after submission.
- A DB error during the write transaction is caught, rolled back, and shown
  in the dialog (not the main window status bar, since the dialog is still
  open) — the dialog stays open with the entered values intact so nothing
  typed is lost.

## Testing & packaging

- `ui/tests/test_writes.py` (new): unit tests against the existing
  `conftest.py`-style temp DuckDB fixture, covering plain insert,
  new-payee auto-create, existing-payee reuse (no duplicate row), new-
  category auto-create, and investment insert with a new security.
- `ui/tests/test_add_record_dialog.py` (new): field visibility switching
  by account type, and OK-button validation gating, following the existing
  convention that widget-level Qt code gets targeted tests where feasible
  (`test_dictionaries_tab.py`) rather than being left entirely to manual
  verification.
- Manual verification: run the app (`./run-ui.sh`), add a cash-account
  record with a new payee and category, add an investment-account record
  with a new security, confirm both appear in the transaction table and
  the corresponding Dictionaries tab.
- No new dependencies.

## Out of scope (this iteration)

- Editing or deleting existing transactions.
- Adding, editing, closing, or deleting accounts.
- Editing/renaming/merging dictionary entries from this feature (payee
  merge already exists separately).
- Preserving manually-added records across a re-extraction from the
  `.mny` file.
- Autocomplete/suggestion beyond exact-prefix `QCompleter` matching (e.g.
  no fuzzy or most-frequent-first ranking).
