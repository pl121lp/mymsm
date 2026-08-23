# Undo Feature — Design

Date: 2026-08-23
Status: Approved for implementation

## Problem

`ui/writes.py` (added in `2026-08-20-add-record-design.md`) lets the
browsing UI add, edit, delete, and bulk-import transactions. All of these
are immediate and permanent — a misclick on "Delete Record" or a bad edit
has no way back short of manually re-entering the data. This adds a
Ctrl+Z undo for the last few record-level writes.

## Constraints & context

Confirmed during brainstorming:

- In scope: add record, edit record, delete record, and bulk import (as
  one undo step per import, not one per imported row).
- Out of scope, permanently: account creation, account deletion, account
  rename, opening-balance edit, and close/reopen. None of these are ever
  pushed to the undo stack.
- The app has no existing edit/audit-history feature to link this to —
  `navigation_history.py` is an unrelated back-button view stack, and the
  account "history" in `main_window.py` is a value-over-time chart.
  Undo does not introduce one either: no visible list of past actions,
  just a single "last action" Ctrl+Z, consistent with how the rest of the
  app has no menu bar, toolbar, or shortcuts today.
- No redo.
- Buffer of 10 events, in-memory only — resets on app restart. Nothing is
  persisted to disk or to `money.duckdb`.
- When undoing an add/edit that auto-created a new Payee/Category/Security
  dictionary entry (via `_find_or_create`), that dictionary entry is left
  in place rather than cleaned up. This matches how Money itself tolerates
  orphan dictionary entries, and it's what makes id-based (not name-based)
  undo safe — see Architecture.
- Trigger is Ctrl+Z only — no menu item, toolbar button, or persistent
  "Undo: ..." indicator. Feedback is a one-off status bar message, the
  same convention already used for add/edit/delete/import confirmations.

## Architecture

```
ui/
  undo.py           (new) UndoStack (bounded deque, maxlen=10) and four
                     command classes: AddCommand, DeleteCommand,
                     EditCommand, ImportCommand.
  writes.py          + restore_transaction(conn, row) — id-preserving
                       insert, used to undo a delete.
                     + delete_transactions(conn, transaction_ids) — batch
                       delete in one transaction, used to undo an import.
                     ~ import_transactions(...) now returns the list of
                       new transaction_ids instead of a count.
  data.py            + get_transaction_row(conn, transaction_id) — plain
                       `SELECT *` by id, no joins, raw ids not names.
  main_window.py     Owns self._undo_stack; a Ctrl+Z QShortcut; each of
                     the 4 write call sites pushes a command after a
                     successful write.
  import_qfx_dialog.py  Exposes imported_transaction_ids alongside the
                     existing imported_count.
```

**Why id-based snapshots, not name-based replay.** An alternative design
would undo a delete by calling `add_transaction` again with the captured
Payee/Category/Security *names*, and undo an edit by calling
`update_transaction` with the captured original names — reusing the
existing public write functions as-is, no new primitives. This was
rejected: `add_transaction` always assigns a fresh `transaction_id`, so a
delete-undo would reinsert the row under a *different* id than it had
before. That breaks a real sequence — edit a record, then delete it, then
press Ctrl+Z twice: the delete-undo reinserts under a new id, so the
still-queued edit-undo (which targets the original id) silently updates
nothing. Capturing the exact row (including its id and its
category_id/payee_id/security_id) and reinserting it verbatim via a new
`restore_transaction` avoids this: every command is self-contained and
correct regardless of what else has happened in between, as long as
commands are undone in strict LIFO order. This is also why leaving
orphaned dictionary entries in place (rather than cleaning them up on
undo) matters: it guarantees a captured id is still valid to reuse
whenever its command is undone.

**Command shapes:**

- `AddCommand(transaction_id)` — undo: `writes.delete_transaction`.
- `DeleteCommand(row)` — undo: `writes.restore_transaction(conn, row)`,
  re-inserting the exact captured row (same transaction_id and same
  category_id/payee_id/security_id).
- `EditCommand(transaction_id, before_row)` — undo: a raw `UPDATE`
  restoring every column on that id to the snapshot values.
- `ImportCommand(transaction_ids)` — undo:
  `writes.delete_transactions(conn, transaction_ids)`.

Each command carries a `description` string (`"Add record"`,
`"Delete record"`, `"Edit record"`, `"Import N record(s)"`) shown in the
post-undo status bar message.

`UndoStack` is a thin wrapper over `collections.deque(maxlen=10)`:
`push`, `pop` (returns `None` when empty), and `__bool__`. No entry point
ever needs to invalidate or inspect entries other than the most recent —
strict LIFO, no redo, so nothing more sophisticated is needed.

## Data flow

Each of the four existing write call sites in `main_window.py` gains one
step: capture what's needed *before* the write (for edit/delete) and push
a command *after* the write succeeds.

1. **Add** (`_on_add_record_button_clicked`): after
   `AddRecordDialog.exec() == Accepted`, if the dialog was in add mode,
   push `AddCommand(dialog.transaction_id)`.
2. **Edit** (the edit handler): call `data.get_transaction_row(conn,
   transaction_id)` before constructing `AddRecordDialog`. After accept,
   push `EditCommand(transaction_id, before_row)`.
3. **Delete** (`_on_delete_record_clicked`): call
   `data.get_transaction_row(conn, transaction_id)` before
   `writes.delete_transaction`. After it succeeds, push
   `DeleteCommand(row)`.
4. **Import** (the import handler): after `ImportQfxDialog.exec() ==
   Accepted`, push `ImportCommand(dialog.imported_transaction_ids)` if
   the list is non-empty.

**Undo** (`main_window._on_undo`, wired to a `QShortcut("Ctrl+Z")`):

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

`_refresh_after_write()` already exists and is fully generic (reloads
accounts, categories, payees, investments panes), so undo needs no new
refresh logic.

## Error handling

- Popping an empty stack is a no-op with a status bar message — not an
  error state.
- If `command.undo(conn)` raises (e.g. a constraint violation), it's
  caught, shown as `f"Failed to undo: {exc}"` in the status bar, and the
  command is **not** re-pushed. It's already been popped and is in an
  unknown state; retrying it on a second Ctrl+Z risks acting on stale
  data, so it's simply dropped and the next-older command becomes the new
  top of the stack.
- `restore_transaction` and `delete_transactions` follow the same
  begin/try/except-rollback/commit pattern already used by
  `add_transaction`, `import_transactions`, and `update_transaction` in
  `writes.py`.

## Testing & packaging

- `ui/tests/test_undo.py` (new), against the existing temp-DuckDB test
  fixture:
  - Each command type: perform the write, push the matching command,
    undo it, assert the table is back to its exact prior state
    (including that `restore_transaction` reproduces the same
    `transaction_id`).
  - The 10-item cap: push 11 commands, assert the oldest was silently
    dropped and only the 10 most recent remain undoable.
  - The edit-then-delete-then-undo-twice sequence specifically, as a
    regression test locking in the id-preservation design decision.
  - Import-undo removes exactly the imported rows and leaves everything
    else (including any dictionary rows the import auto-created)
    untouched.
- `ui/tests/test_writes.py`: extend for `restore_transaction`,
  `delete_transactions`, and the `import_transactions` return-value
  change.
- Manual verification: run the app (`./run-ui.sh`), add/edit/delete a
  record and Ctrl+Z each; import a QFX file and Ctrl+Z the whole import;
  confirm the status bar messages and that Ctrl+Z with nothing to undo
  is a harmless no-op.
- No new dependencies.

## Out of scope (this iteration)

- Redo.
- Any visible list/panel of undoable actions — Ctrl+Z only.
- Undo for account creation, deletion, rename, opening-balance edit, or
  close/reopen.
- Undo surviving an app restart.
- Cleaning up dictionary entries (Payee/Category/Security) that were
  auto-created by an add/edit/import once that action is undone.
- Menu bar, toolbar, or any keyboard shortcut other than Ctrl+Z.
