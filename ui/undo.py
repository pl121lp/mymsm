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


class AddGrantCommand:
    def __init__(self, transaction_ids):
        self.transaction_ids = transaction_ids
        self.description = f"Add grant ({len(transaction_ids)} record(s))"

    def undo(self, conn):
        writes.delete_transactions(conn, self.transaction_ids)
