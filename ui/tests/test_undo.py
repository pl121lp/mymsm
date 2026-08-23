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
