# Undo Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Ctrl+Z undo for the last few record-level writes (add, edit, delete, import) in the desktop browsing UI, without touching account-level writes (create/delete/rename/balance/close/reopen), which stay permanent.

**Architecture:** A bounded (10-item) LIFO command stack (`ui/undo.py`) holds one command object per undoable write. Each command captures the exact `transactions` row (by id, including its `category_id`/`payee_id`/`security_id`) needed to reverse itself, using three new mutation primitives added to `ui/writes.py` and one new read primitive added to `ui/data.py`. `main_window.py` pushes a command right after each of its four write call sites succeeds, and a Ctrl+Z `QShortcut` pops and undoes the most recent one.

**Tech Stack:** Python, PySide6 (Qt), DuckDB, pytest (existing stack — no new dependencies).

**Spec:** `docs/superpowers/specs/2026-08-23-undo-feature-design.md`

## Global Constraints

- Undo buffer is in-memory only, capped at 10 entries, oldest dropped first — no persistence across app restarts.
- No redo.
- Only these four operations are undoable: add record, edit record, delete record, bulk import. Account creation, deletion, rename, opening-balance edit, and close/reopen are never pushed to the stack.
- Undoing an add/edit/import never removes an auto-created Payee/Category/Security dictionary entry — dictionary rows are left in place even if now unused.
- Trigger is Ctrl+Z only — no menu, toolbar, or persistent "Undo: ..." indicator. Feedback is a one-off status bar message, matching the existing convention (`"Record added."`, `"Record deleted."`, etc.).
- All `money.duckdb` mutation stays in `ui/writes.py` (existing project invariant, stated in that module's docstring); `ui/data.py` stays read-only; `ui/undo.py` holds no SQL of its own, only command objects that call into `writes.py`.

---

### Task 1: `writes.py` id-preserving undo primitives + `import_transactions` return-type change

**Files:**
- Modify: `ui/writes.py`
- Modify: `ui/import_qfx_dialog.py:65,180-186`
- Test: `ui/tests/test_writes.py`
- Test: `ui/tests/test_import_qfx_dialog.py:73-83`

**Interfaces:**
- Produces: `writes.restore_transaction(conn, row: tuple) -> None` — re-inserts a 12-column transaction row exactly as returned by `data.get_transaction_row` (Task 2), preserving `transaction_id`.
- Produces: `writes.restore_transaction_fields(conn, row: tuple) -> None` — raw `UPDATE` restoring `category_id, payee_id, txn_date, amount, memo, security_id, activity, quantity, price` on `row[0]` (the `transaction_id`), from a 12-column row of the same shape.
- Produces: `writes.delete_transactions(conn, transaction_ids: list[int]) -> None` — batch delete, one DB transaction.
- Changes: `writes.import_transactions(...)` now returns `list[int]` (the new transaction_ids, in insertion order) instead of `int`.
- Changes: `ImportQfxDialog.imported_count` stays an `int` (now `len(ids)`); adds `ImportQfxDialog.imported_transaction_ids: list[int]`.

The 12-column row shape (matches the `transactions` table exactly, see `etl/schema.py:31-44`):
`(transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, security_id, activity, quantity, price, linked_account_id)`.

- [ ] **Step 1: Write failing tests for `restore_transaction`**

Add to `ui/tests/test_writes.py` (add `restore_transaction` to the existing `from writes import (...)` block at the top):

```python
def test_restore_transaction_reinserts_deleted_row_with_same_id(conn):
    row = conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    delete_transaction(conn, transaction_id=1000)

    restore_transaction(conn, row)

    restored = conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    assert restored == row


def test_restore_transaction_leaves_other_rows_intact(conn):
    row = conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    delete_transaction(conn, transaction_id=1000)

    restore_transaction(conn, row)

    other = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id = 1001"
    ).fetchone()
    assert other == (1001,)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest ui/tests/test_writes.py -k restore_transaction -v`
Expected: FAIL with `ImportError: cannot import name 'restore_transaction'`

- [ ] **Step 3: Implement `restore_transaction`**

In `ui/writes.py`, add after `delete_transaction` (after line 68):

```python
def restore_transaction(conn, row):
    """Re-inserts a previously-deleted transaction row exactly as captured
    by data.get_transaction_row, preserving its original transaction_id
    and dictionary ids (category_id/payee_id/security_id). Used only to
    undo delete_transaction — see ui/undo.py."""
    conn.execute(
        "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", list(row)
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest ui/tests/test_writes.py -k restore_transaction -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Write failing tests for `restore_transaction_fields`**

Add to `ui/tests/test_writes.py` (add `restore_transaction_fields` to the import block):

```python
def test_restore_transaction_fields_reverts_an_edit(conn):
    before = conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    update_transaction(
        conn, transaction_id=1000, txn_date=date(2024, 4, 2), amount=Decimal("-99.00"),
        memo="edited",
    )

    restore_transaction_fields(conn, before)

    after = conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    assert after == before


def test_restore_transaction_fields_does_not_touch_account_id_or_transaction_id(conn):
    before = conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = 1000"
    ).fetchone()

    restore_transaction_fields(conn, before)  # no prior edit — should be a no-op

    after = conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    assert after == before
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `.venv/bin/pytest ui/tests/test_writes.py -k restore_transaction_fields -v`
Expected: FAIL with `ImportError: cannot import name 'restore_transaction_fields'`

- [ ] **Step 7: Implement `restore_transaction_fields`**

In `ui/writes.py`, add after `restore_transaction`:

```python
def restore_transaction_fields(conn, row):
    """Restores the mutable fields of an existing transaction (everything
    update_transaction can change) to a previously captured snapshot, by
    raw id rather than by name — no dictionary lookup or auto-create.
    Used only to undo update_transaction — see ui/undo.py."""
    (
        transaction_id, _account_id, category_id, payee_id, txn_date, amount, memo,
        security_id, activity, quantity, price, _linked_account_id,
    ) = row
    conn.execute(
        "UPDATE transactions SET category_id = ?, payee_id = ?, txn_date = ?, amount = ?, "
        "memo = ?, security_id = ?, activity = ?, quantity = ?, price = ? "
        "WHERE transaction_id = ?",
        [category_id, payee_id, txn_date, amount, memo, security_id, activity, quantity, price, transaction_id],
    )
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `.venv/bin/pytest ui/tests/test_writes.py -k restore_transaction_fields -v`
Expected: PASS (2 tests)

- [ ] **Step 9: Write failing tests for `delete_transactions`**

Add to `ui/tests/test_writes.py` (add `delete_transactions` to the import block):

```python
def test_delete_transactions_removes_all_given_ids(conn):
    delete_transactions(conn, [1000, 1001])
    rows = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id IN (1000, 1001)"
    ).fetchall()
    assert rows == []


def test_delete_transactions_leaves_other_rows_intact(conn):
    delete_transactions(conn, [1000])
    row = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id = 1001"
    ).fetchone()
    assert row == (1001,)


def test_delete_transactions_does_nothing_for_empty_list(conn):
    before_count = len(data.list_transactions(conn, account_id=1))
    delete_transactions(conn, [])
    assert len(data.list_transactions(conn, account_id=1)) == before_count
```

- [ ] **Step 10: Run tests to verify they fail**

Run: `.venv/bin/pytest ui/tests/test_writes.py -k delete_transactions -v`
Expected: FAIL with `ImportError: cannot import name 'delete_transactions'`

- [ ] **Step 11: Implement `delete_transactions`**

In `ui/writes.py`, add after `restore_transaction_fields`:

```python
def delete_transactions(conn, transaction_ids):
    """Permanently deletes multiple transaction rows in one transaction —
    all-or-nothing, like import_transactions' insert side. Used only to
    undo import_transactions — see ui/undo.py."""
    if not transaction_ids:
        return
    conn.begin()
    try:
        for transaction_id in transaction_ids:
            conn.execute("DELETE FROM transactions WHERE transaction_id = ?", [transaction_id])
    except Exception:
        conn.rollback()
        raise
    conn.commit()
```

- [ ] **Step 12: Run tests to verify they pass**

Run: `.venv/bin/pytest ui/tests/test_writes.py -k delete_transactions -v`
Expected: PASS (3 tests)

- [ ] **Step 13: Update the two existing `import_transactions` tests that assert on the old `int` return value, and add one for the new shape**

In `ui/tests/test_writes.py`, change `test_import_transactions_inserts_one_row_per_record` (previously asserting `count == 2`):

```python
def test_import_transactions_inserts_one_row_per_record(conn):
    records = [
        _qfx_record(name="Store A", amount="-5.00", txn_date=date(2024, 4, 1)),
        _qfx_record(name="New Cafe", amount="-9.00", txn_date=date(2024, 4, 2)),
    ]

    transaction_ids = import_transactions(conn, account_id=1, records=records)

    assert len(transaction_ids) == 2
    rows = conn.execute(
        "SELECT t.txn_date, t.amount, t.memo, p.name FROM transactions t "
        "JOIN payees p ON p.payee_id = t.payee_id "
        "WHERE t.account_id = 1 AND t.txn_date IN ('2024-04-01', '2024-04-02') "
        "ORDER BY t.txn_date"
    ).fetchall()
    assert rows == [
        (date(2024, 4, 1), Decimal("-5.00"), "a memo", "Store A"),
        (date(2024, 4, 2), Decimal("-9.00"), "a memo", "New Cafe"),
    ]
```

Change `test_import_transactions_returns_zero_for_empty_list`:

```python
def test_import_transactions_returns_empty_list_for_empty_records(conn):
    assert import_transactions(conn, account_id=1, records=[]) == []
```

Add a new test asserting the ids are the actual new transaction ids, right after `test_import_transactions_uses_sequential_ids_after_max`:

```python
def test_import_transactions_returns_the_new_transaction_ids(conn):
    # conn fixture seeds transaction_ids up to 3003 (see conftest.py).
    records = [_qfx_record(), _qfx_record(txn_date=date(2024, 4, 2))]
    transaction_ids = import_transactions(conn, account_id=1, records=records)
    assert sorted(transaction_ids) == [3004, 3005]
```

- [ ] **Step 14: Update the implementation to return the ids**

In `ui/writes.py`, modify `import_transactions` (currently lines 116-141): change the loop to collect ids and change the return statement.

```python
def import_transactions(conn, account_id, records):
    """Bulk-inserts parsed QFX records into account_id as plain cash rows
    (payee = record.name, memo = record.memo), auto-creating any payee that
    doesn't already exist by name (case-insensitive). The whole batch commits
    as one transaction, so a bad row can't leave the account half-imported.
    Returns the list of new transaction_ids, in insertion order."""
    if not records:
        return []
    conn.begin()
    try:
        transaction_id = _next_id(conn, "transactions", "transaction_id")
        transaction_ids = []
        for record in records:
            payee_id = _find_or_create(conn, "payees", "payee_id", record.name) if record.name else None
            conn.execute(
                "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)",
                [
                    transaction_id, account_id, None, payee_id, record.txn_date, record.amount,
                    record.memo or None, None, None, None, None,
                ],
            )
            transaction_ids.append(transaction_id)
            transaction_id += 1
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return transaction_ids
```

- [ ] **Step 15: Run the full test_writes.py suite to verify everything passes**

Run: `.venv/bin/pytest ui/tests/test_writes.py -v`
Expected: PASS, all tests

- [ ] **Step 16: Update `ImportQfxDialog` to expose the new ids and fix its one caller of `import_transactions`**

In `ui/import_qfx_dialog.py`, change line 65 (`self.imported_count = 0`) to also initialize the new attribute:

```python
        self.imported_count = 0
        self.imported_transaction_ids = []
```

Change `_on_apply` (lines 177-186):

```python
    def _on_apply(self):
        account_id = self.account_combo.currentData()
        try:
            self.imported_transaction_ids = writes.import_transactions(
                self._conn, account_id, self._to_import
            )
        except Exception as exc:
            self.error_label.setText(f"Failed to import records: {exc}")
            return
        self.imported_count = len(self.imported_transaction_ids)
        self.accept()
```

- [ ] **Step 17: Update the one existing test that reads `imported_count` after `_on_apply`, and add a test for the new attribute**

In `ui/tests/test_import_qfx_dialog.py`, find `test_apply_inserts_only_non_duplicate_records_and_accepts` (lines 73-83) and add an assertion after the existing `assert dialog.imported_count == 1`:

```python
    assert dialog.imported_count == 1
    assert len(dialog.imported_transaction_ids) == 1
```

- [ ] **Step 18: Run the full import_qfx_dialog test suite and the whole ui/tests directory**

Run: `.venv/bin/pytest ui/tests/test_import_qfx_dialog.py ui/tests/test_writes.py -v`
Expected: PASS, all tests

- [ ] **Step 19: Commit**

```bash
git add ui/writes.py ui/import_qfx_dialog.py ui/tests/test_writes.py ui/tests/test_import_qfx_dialog.py
git commit -m "feat: add id-preserving undo primitives to writes.py"
```

---

### Task 2: `data.py` raw row snapshot helper

**Files:**
- Modify: `ui/data.py`
- Test: `ui/tests/test_data.py`

**Interfaces:**
- Consumes: nothing new (plain query against the existing `transactions` table).
- Produces: `data.get_transaction_row(conn, transaction_id: int) -> tuple | None` — returns
  `(transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, security_id, activity, quantity, price, linked_account_id)`, raw ids (no joins), or `None` if the id doesn't exist. This is the exact row shape `writes.restore_transaction` and `writes.restore_transaction_fields` (Task 1) expect.

- [ ] **Step 1: Write the failing test**

`ui/tests/test_data.py` imports each function it tests by name — `from data import (count_transactions_by_payee, list_accounts, ...)` (an alphabetized multi-line list) — and calls it unqualified (e.g. `list_transactions(conn, ...)`), never with a `data.` prefix. Add `get_transaction_row` into that same alphabetized `from data import (...)` list, then add to `ui/tests/test_data.py`:

```python
def test_get_transaction_row_returns_all_raw_columns(conn):
    row = get_transaction_row(conn, transaction_id=1000)
    assert row == (
        1000, 1, 10, 100, date(2024, 3, 15), Decimal("-52.30"), "weekly shop",
        None, None, None, None, None,
    )


def test_get_transaction_row_returns_none_for_unknown_id(conn):
    assert get_transaction_row(conn, transaction_id=999999) is None
```

(`transaction_id=1000` and its column values come from the `conn` fixture in `ui/tests/conftest.py`; `date` and `Decimal` are already imported at the top of `ui/tests/test_data.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/bin/pytest ui/tests/test_data.py -k get_transaction_row -v`
Expected: FAIL with `ImportError: cannot import name 'get_transaction_row' from 'data'`

- [ ] **Step 3: Implement `get_transaction_row`**

In `ui/data.py`, add after `list_transactions` (after line 97):

```python
def get_transaction_row(conn: duckdb.DuckDBPyConnection, transaction_id: int) -> tuple | None:
    """Raw (unjoined) transaction row, ids not names — a snapshot used by
    ui/undo.py to reverse an edit or delete. Column order matches the
    transactions table exactly (see etl/schema.py)."""
    return conn.execute(
        "SELECT transaction_id, account_id, category_id, payee_id, txn_date, amount, memo, "
        "security_id, activity, quantity, price, linked_account_id "
        "FROM transactions WHERE transaction_id = ?",
        [transaction_id],
    ).fetchone()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/bin/pytest ui/tests/test_data.py -k get_transaction_row -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Run the full test_data.py suite**

Run: `.venv/bin/pytest ui/tests/test_data.py -v`
Expected: PASS, all tests

- [ ] **Step 6: Commit**

```bash
git add ui/data.py ui/tests/test_data.py
git commit -m "feat: add data.get_transaction_row for undo snapshots"
```

---

### Task 3: `ui/undo.py` — command stack and command types

**Files:**
- Create: `ui/undo.py`
- Test: `ui/tests/test_undo.py`

**Interfaces:**
- Consumes: `writes.delete_transaction`, `writes.restore_transaction`, `writes.restore_transaction_fields`, `writes.delete_transactions` (Task 1); `data.get_transaction_row` (Task 2) — used only in this task's tests, not by `undo.py` itself (snapshot capture happens in `main_window.py`, Task 4).
- Produces:
  - `UndoStack(maxlen=10)` with `.push(command)`, `.pop() -> command | None`, `.__bool__()`.
  - `AddCommand(transaction_id: int)` — `.description == "Add record"`, `.undo(conn)`.
  - `DeleteCommand(row: tuple)` — `.description == "Delete record"`, `.undo(conn)`.
  - `EditCommand(before_row: tuple)` — `.description == "Edit record"`, `.undo(conn)`.
  - `ImportCommand(transaction_ids: list[int])` — `.description == f"Import {len(transaction_ids)} record(s)"`, `.undo(conn)`.
  - All four `row`/`before_row` arguments are the 12-column shape from `data.get_transaction_row` (Task 2).

- [ ] **Step 1: Write the failing tests**

Create `ui/tests/test_undo.py`:

```python
"""Tests for ui/undo.py — the command stack behind Ctrl+Z."""

from datetime import date
from decimal import Decimal

import data
import writes
from undo import AddCommand, DeleteCommand, EditCommand, ImportCommand, UndoStack


def test_undo_stack_pop_on_empty_returns_none():
    stack = UndoStack()
    assert stack.pop() is None


def test_undo_stack_pop_returns_most_recently_pushed():
    stack = UndoStack()
    stack.push("first")
    stack.push("second")
    assert stack.pop() == "second"
    assert stack.pop() == "first"
    assert stack.pop() is None


def test_undo_stack_bool_reflects_emptiness():
    stack = UndoStack()
    assert not stack
    stack.push("x")
    assert stack
    stack.pop()
    assert not stack


def test_undo_stack_drops_oldest_beyond_maxlen():
    stack = UndoStack(maxlen=10)
    for i in range(11):
        stack.push(i)
    popped = [stack.pop() for _ in range(10)]
    assert popped == list(range(10, 0, -1))  # 10 down to 1 — item 0 was dropped
    assert stack.pop() is None


def test_add_command_undo_deletes_the_added_transaction(conn):
    transaction_id = writes.add_transaction(
        conn, account_id=1, txn_date=date(2024, 4, 1), amount=Decimal("-10.00"),
    )
    command = AddCommand(transaction_id)

    command.undo(conn)

    row = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id = ?", [transaction_id]
    ).fetchone()
    assert row is None


def test_delete_command_undo_restores_the_exact_row(conn):
    before_row = data.get_transaction_row(conn, transaction_id=1000)
    writes.delete_transaction(conn, transaction_id=1000)
    command = DeleteCommand(before_row)

    command.undo(conn)

    assert data.get_transaction_row(conn, transaction_id=1000) == before_row


def test_edit_command_undo_restores_prior_field_values(conn):
    before_row = data.get_transaction_row(conn, transaction_id=1000)
    writes.update_transaction(
        conn, transaction_id=1000, txn_date=date(2024, 4, 2), amount=Decimal("-99.00"),
        memo="edited",
    )
    command = EditCommand(before_row)

    command.undo(conn)

    assert data.get_transaction_row(conn, transaction_id=1000) == before_row


def test_import_command_undo_removes_all_imported_ids(conn):
    from qfx_import import QfxRecord

    records = [
        QfxRecord(
            trn_type="DEBIT", txn_date=date(2024, 4, 1), amount=Decimal("-1.00"),
            fitid="1", name="A", memo="", checknum="",
        ),
        QfxRecord(
            trn_type="DEBIT", txn_date=date(2024, 4, 2), amount=Decimal("-2.00"),
            fitid="2", name="B", memo="", checknum="",
        ),
    ]
    transaction_ids = writes.import_transactions(conn, account_id=1, records=records)
    command = ImportCommand(transaction_ids)

    command.undo(conn)

    rows = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id IN (?, ?)",
        transaction_ids,
    ).fetchall()
    assert rows == []
    # transaction 1000, seeded by the conn fixture, is untouched
    untouched = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id = 1000"
    ).fetchone()
    assert untouched == (1000,)


def test_import_command_description_mentions_the_count():
    command = ImportCommand([3004, 3005, 3006])
    assert command.description == "Import 3 record(s)"


def test_edit_then_delete_then_undo_twice_restores_original_row(conn):
    """Regression test for the id-drift bug that ruled out the
    name-based-replay design (see the design spec's Architecture section):
    edit a transaction, then delete it, then undo twice. The delete-undo
    must reinsert under the *original* transaction_id so the still-queued
    edit-undo (targeting that same id) has something to act on."""
    original_row = data.get_transaction_row(conn, transaction_id=1000)

    edit_before_row = data.get_transaction_row(conn, transaction_id=1000)
    writes.update_transaction(
        conn, transaction_id=1000, txn_date=date(2024, 4, 2), amount=Decimal("-99.00"),
        memo="edited",
    )
    edit_command = EditCommand(edit_before_row)

    delete_before_row = data.get_transaction_row(conn, transaction_id=1000)
    writes.delete_transaction(conn, transaction_id=1000)
    delete_command = DeleteCommand(delete_before_row)

    stack = UndoStack()
    stack.push(edit_command)
    stack.push(delete_command)

    stack.pop().undo(conn)  # undoes the delete: row 1000 reappears, edited
    stack.pop().undo(conn)  # undoes the edit: row 1000 back to its original values

    assert data.get_transaction_row(conn, transaction_id=1000) == original_row
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest ui/tests/test_undo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'undo'`

- [ ] **Step 3: Implement `ui/undo.py`**

Create `ui/undo.py`:

```python
"""Undo support for the last few record-level writes in the browsing UI.

Each command captures exactly what's needed to reverse one write
(add/edit/delete/import) by raw transaction id, so that undoing one
command never depends on what other commands are still queued. UndoStack
keeps the most recent ones (bounded, oldest dropped first) and pops them
in strict LIFO order — there's no redo. See
docs/superpowers/specs/2026-08-23-undo-feature-design.md for the full
design and the id-drift bug this specifically avoids.
"""

from collections import deque

import writes


class UndoStack:
    def __init__(self, maxlen=10):
        self._stack = deque(maxlen=maxlen)

    def push(self, command):
        self._stack.append(command)

    def pop(self):
        if not self._stack:
            return None
        return self._stack.pop()

    def __bool__(self):
        return bool(self._stack)


class AddCommand:
    description = "Add record"

    def __init__(self, transaction_id):
        self.transaction_id = transaction_id

    def undo(self, conn):
        writes.delete_transaction(conn, self.transaction_id)


class DeleteCommand:
    description = "Delete record"

    def __init__(self, row):
        self._row = row

    def undo(self, conn):
        writes.restore_transaction(conn, self._row)


class EditCommand:
    description = "Edit record"

    def __init__(self, before_row):
        self._before_row = before_row

    def undo(self, conn):
        writes.restore_transaction_fields(conn, self._before_row)


class ImportCommand:
    def __init__(self, transaction_ids):
        self.transaction_ids = transaction_ids
        self.description = f"Import {len(transaction_ids)} record(s)"

    def undo(self, conn):
        writes.delete_transactions(conn, self.transaction_ids)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest ui/tests/test_undo.py -v`
Expected: PASS, all tests

- [ ] **Step 5: Commit**

```bash
git add ui/undo.py ui/tests/test_undo.py
git commit -m "feat: add undo command stack (ui/undo.py)"
```

---

### Task 4: Wire undo into `main_window.py`

**Files:**
- Modify: `ui/main_window.py:8,30-49,74-77,332-352,439-459,461-485,380-386`
- Test: `ui/tests/test_main_window.py`

**Interfaces:**
- Consumes: `UndoStack`, `AddCommand`, `DeleteCommand`, `EditCommand`, `ImportCommand` (Task 3); `data.get_transaction_row` (Task 2); `dialog.imported_transaction_ids` (Task 1).
- Produces: `MainWindow._undo_stack: UndoStack` (instance attribute); `MainWindow._on_undo(self) -> None`, wired to `Ctrl+Z`.

- [ ] **Step 1: Write the failing tests**

Add to `ui/tests/test_main_window.py`:

```python
def test_undo_with_nothing_to_undo_shows_status_message(qapp, conn):
    window = MainWindow(conn)
    window._on_undo()
    assert window.statusBar().currentMessage() == "Nothing to undo."


def test_ctrl_z_undoes_an_add(qapp, conn, monkeypatch):
    import add_record_dialog
    import writes
    from datetime import date
    from decimal import Decimal

    def fake_exec(self):
        self.transaction_id = writes.add_transaction(
            self._conn, self._account_id, date(2024, 4, 1), Decimal("-5.00"),
        )
        return QDialog.Accepted

    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", fake_exec)

    window = MainWindow(conn)
    window.account_view.selectRow(1)  # row 1 = Checking (cash account, see conn fixture ordering)
    window._on_add_record_button_clicked()
    new_id = window.transaction_model.transaction_at(0)[0]

    window._on_undo()

    row = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id = ?", [new_id]
    ).fetchone()
    assert row is None
    assert window.statusBar().currentMessage() == "Undone: Add record"


def test_ctrl_z_undoes_an_edit(qapp, conn, monkeypatch):
    import add_record_dialog

    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", lambda self: QDialog.Accepted)

    window = MainWindow(conn)
    window.account_view.selectRow(1)
    original_memo = conn.execute(
        "SELECT memo FROM transactions WHERE transaction_id = 1000"
    ).fetchone()[0]

    window._on_transaction_double_clicked(window.transaction_model.index(0, 0))
    conn.execute("UPDATE transactions SET memo = 'clobbered' WHERE transaction_id = 1000")

    window._on_undo()

    memo = conn.execute("SELECT memo FROM transactions WHERE transaction_id = 1000").fetchone()[0]
    assert memo == original_memo
    assert window.statusBar().currentMessage() == "Undone: Edit record"


def test_ctrl_z_undoes_a_delete(qapp, conn, monkeypatch):
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.Yes)

    window = MainWindow(conn)
    window.account_view.selectRow(1)
    transaction_id = window.transaction_model.transaction_at(0)[0]

    window._on_delete_record_clicked(0)
    window._on_undo()

    row = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id = ?", [transaction_id]
    ).fetchone()
    assert row is not None
    assert window.statusBar().currentMessage() == "Undone: Delete record"


def test_ctrl_z_undoes_an_import(qapp, conn, monkeypatch):
    import import_qfx_dialog
    import main_window

    def fake_exec(self):
        self.imported_transaction_ids = [9001, 9002]
        self.imported_count = 2
        conn.execute(
            "INSERT INTO transactions VALUES "
            "(9001, 1, NULL, NULL, '2024-05-01', -1.00, NULL, NULL, NULL, NULL, NULL, NULL), "
            "(9002, 1, NULL, NULL, '2024-05-02', -2.00, NULL, NULL, NULL, NULL, NULL, NULL)"
        )
        return QDialog.Accepted

    monkeypatch.setattr(import_qfx_dialog.ImportQfxDialog, "exec", fake_exec)
    # non-empty return, contents unused by fake_exec
    monkeypatch.setattr(main_window, "parse_qfx", lambda path: [object()])
    monkeypatch.setattr(
        main_window.QFileDialog, "getOpenFileName", lambda *a, **kw: ("dummy.qfx", "")
    )

    window = MainWindow(conn)
    window.account_view.selectRow(1)

    window._on_import_button_clicked()
    window._on_undo()

    rows = conn.execute(
        "SELECT transaction_id FROM transactions WHERE transaction_id IN (9001, 9002)"
    ).fetchall()
    assert rows == []
    assert window.statusBar().currentMessage() == "Undone: Import 2 record(s)"


def test_ctrl_z_shortcut_is_wired_to_on_undo(qapp, conn):
    window = MainWindow(conn)
    shortcuts = [
        sc for sc in window.findChildren(QShortcut) if sc.key() == QKeySequence("Ctrl+Z")
    ]
    assert len(shortcuts) == 1
```

Add one import at the top of `ui/tests/test_main_window.py`: `from PySide6.QtGui import QKeySequence, QShortcut`. No other top-level import is needed — `test_ctrl_z_undoes_an_import` reaches `QFileDialog` and `parse_qfx` via a local `import main_window` inside the test function, matching the existing convention already used by e.g. `test_import_button_does_nothing_when_no_file_selected` (`ui/tests/test_main_window.py:150-157`): `monkeypatch.setattr(main_window.QFileDialog, "getOpenFileName", ...)` and `monkeypatch.setattr(main_window, "parse_qfx", ...)`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest ui/tests/test_main_window.py -k "undo or ctrl_z" -v`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_on_undo'` (and similar) for every test above.

- [ ] **Step 3: Add imports**

In `ui/main_window.py`, change line 8:

```python
from PySide6.QtGui import QKeySequence, QPainter, QShortcut
```

Add near the other local-module imports (after line 39, `from import_qfx_dialog import ImportQfxDialog`):

```python
from undo import AddCommand, DeleteCommand, EditCommand, ImportCommand, UndoStack
```

- [ ] **Step 4: Wire up the stack and the shortcut in `__init__`**

In `ui/main_window.py`, change lines 74-77:

```python
        self._history = NavigationHistory()
        self._current_view = None
        self._navigating_back = False
        self._undo_stack = UndoStack()
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._on_undo)
        QApplication.instance().installEventFilter(self)
```

- [ ] **Step 5: Add `_on_undo`**

In `ui/main_window.py`, add after `_refresh_after_write` (after line 336):

```python
    def _on_undo(self):
        command = self._undo_stack.pop()
        if command is None:
            self.statusBar().showMessage("Nothing to undo.")
            return
        try:
            command.undo(self._conn)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to undo: {exc}")
            return
        self._refresh_after_write()
        self.statusBar().showMessage(f"Undone: {command.description}")
```

- [ ] **Step 6: Push a command from the add-record call site**

In `ui/main_window.py`, change `_on_add_record_button_clicked` (lines 338-352):

```python
    def _on_add_record_button_clicked(self):
        indexes = self.account_view.selectionModel().selectedRows()
        if not indexes:
            return
        row = indexes[0].row()
        account_id, _name, account_type, _currency, _balance, _is_closed = self.account_model.account_at(
            row
        )
        dialog = AddRecordDialog(self._conn, account_id, account_type, parent=self)
        if dialog.exec() != AddRecordDialog.Accepted:
            return
        self._undo_stack.push(AddCommand(dialog.transaction_id))
        self._refresh_after_write()
        self.account_view.selectRow(row)
        self._on_account_selected()
        self.statusBar().showMessage("Record added.")
```

- [ ] **Step 7: Push a command from the edit call site**

In `ui/main_window.py`, change `_edit_transaction` (lines 439-459):

```python
    def _edit_transaction(self, row):
        indexes = self.account_view.selectionModel().selectedRows()
        if not indexes:
            return
        account_row = indexes[0].row()
        account_id, _name, account_type, _currency, _balance, _is_closed = self.account_model.account_at(
            account_row
        )
        transaction = self.transaction_model.transaction_at(row)
        if transaction[0] is None:
            self.statusBar().showMessage(
                "Interest records are derived from another account and can't be edited here."
            )
            return
        before_row = data.get_transaction_row(self._conn, transaction[0])
        dialog = AddRecordDialog(self._conn, account_id, account_type, transaction=transaction, parent=self)
        if dialog.exec() != AddRecordDialog.Accepted:
            return
        self._undo_stack.push(EditCommand(before_row))
        self._refresh_after_write()
        self.account_view.selectRow(account_row)
        self._on_account_selected()
        self.statusBar().showMessage("Record updated.")
```

- [ ] **Step 8: Push a command from the delete call site, and fix the now-inaccurate confirmation text**

In `ui/main_window.py`, change `_on_delete_record_clicked` (lines 466-485):

```python
    def _on_delete_record_clicked(self, row):
        indexes = self.account_view.selectionModel().selectedRows()
        if not indexes:
            return
        account_row = indexes[0].row()
        transaction_id = self.transaction_model.transaction_at(row)[0]
        reply = QMessageBox.question(
            self,
            "Delete Record",
            "Permanently delete this record? Press Ctrl+Z afterward to undo.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        before_row = data.get_transaction_row(self._conn, transaction_id)
        writes.delete_transaction(self._conn, transaction_id)
        self._undo_stack.push(DeleteCommand(before_row))
        self._refresh_after_write()
        self.account_view.selectRow(account_row)
        self._on_account_selected()
        self.statusBar().showMessage("Record deleted.")
```

- [ ] **Step 9: Push a command from the import call site**

In `ui/main_window.py`, change the tail of `_on_import_button_clicked` (lines 380-386):

```python
        dialog = ImportQfxDialog(
            self._conn, records, default_account_id=default_account_id, parent=self
        )
        if dialog.exec() != ImportQfxDialog.Accepted:
            return
        if dialog.imported_transaction_ids:
            self._undo_stack.push(ImportCommand(dialog.imported_transaction_ids))
        self._refresh_after_write()
        self.statusBar().showMessage(f"Imported {dialog.imported_count} transaction(s).")
```

- [ ] **Step 10: Run the new undo tests**

Run: `.venv/bin/pytest ui/tests/test_main_window.py -k "undo or ctrl_z" -v`
Expected: PASS, all tests

- [ ] **Step 11: Run the full main_window test suite**

Run: `.venv/bin/pytest ui/tests/test_main_window.py -v`
Expected: PASS, all tests (confirms the confirmation-text change and the added `before_row` lookups didn't break any existing add/edit/delete/import behavior)

- [ ] **Step 12: Run the entire `ui/tests` suite**

Run: `.venv/bin/pytest ui/tests -v`
Expected: PASS, all tests

- [ ] **Step 13: Manual verification**

Run: `./run-ui.sh`
- Add a record, press Ctrl+Z → it disappears, status bar shows "Undone: Add record".
- Edit a record's memo, press Ctrl+Z → memo reverts, status bar shows "Undone: Edit record".
- Delete a record, press Ctrl+Z → it reappears, status bar shows "Undone: Delete record".
- Import a QFX file, press Ctrl+Z → all imported rows disappear in one step, status bar shows "Undone: Import N record(s)".
- Press Ctrl+Z with nothing pending → status bar shows "Nothing to undo."
- Confirm account-level actions (close/reopen, delete account, rename, new account) are unaffected — Ctrl+Z never reaches back before the first record-level write in the session.

- [ ] **Step 14: Commit**

```bash
git add ui/main_window.py ui/tests/test_main_window.py
git commit -m "feat: wire Ctrl+Z undo into the main window"
```

---

## Self-Review Notes

- **Spec coverage:** add/edit/delete/import undo (Tasks 1, 3, 4); 10-item cap and no persistence (Task 3's `UndoStack`, default `maxlen=10`, in-memory `deque`); no redo (no redo method anywhere); account-level writes excluded (never touched in any task); dictionary entries left in place (no cleanup code anywhere — `restore_transaction`/`restore_transaction_fields` operate purely on already-known ids, never call `_find_or_create`); Ctrl+Z-only trigger with status bar feedback (Task 4, Steps 4-5); id-drift regression test (Task 3, `test_edit_then_delete_then_undo_twice_restores_original_row`). All spec sections are covered.
- **Type consistency:** `AddCommand`/`DeleteCommand`/`EditCommand`/`ImportCommand` constructor signatures and `.description`/`.undo(conn)` shape are defined once in Task 3 and used identically in Task 4's call sites. `data.get_transaction_row` and `writes.restore_transaction`/`restore_transaction_fields` all agree on the same 12-column tuple order (defined once in Task 2, reused in Tasks 1, 3, 4).
