# Add Record to Account Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user add a transaction to an account from the desktop UI, auto-creating any new Payee/Category/Security dictionary entry by name, with autocomplete against existing dictionary values.

**Architecture:** A new `ui/writes.py` module holds all `money.duckdb` mutation (transaction-wrapped insert + find-or-create dictionary lookups); a new `ui/add_record_dialog.py` modal `QDialog` collects the fields (Payee/Category for cash accounts, Security/Activity/Quantity/Price for investment accounts) and calls into `writes.py`; `ui/main_window.py` gains an "Add Record" row-action button that opens the dialog and reloads the account on success; `ui/main.py` drops the read-only connection flag.

**Tech Stack:** Python 3 (existing project `.venv`), PySide6 (Qt6 bindings), DuckDB (existing `duckdb` package), pytest.

**Spec:** `docs/superpowers/specs/2026-08-20-add-record-design.md`

## Global Constraints

- `data.py` stays read-only/query-only (its module docstring says "Read-only: no writes here") — all mutation lives in the new `writes.py`, never added to `data.py`.
- New transaction/category/payee/security IDs use `MAX(id)+1` per table (not a negative-ID range).
- Both cash-type accounts (Payee/Category/Memo/Amount) and investment accounts (Security/Activity/Quantity/Price/Amount/Memo) are in scope.
- Entry UX is a modal dialog, not inline table-row editing.
- Amount/Quantity/Price are parsed as `Decimal`, matching the schema's `DECIMAL` columns.
- Re-running `./extract-data-to-db.sh` will still wipe manually-added records — no changes to `etl/load.py` or `etl/schema.py`.
- No new dependencies; everything is already-installed `PySide6`/`duckdb`.

---

### Task 1: Write layer (`ui/writes.py`)

**Files:**
- Create: `ui/writes.py`
- Test: `ui/tests/test_writes.py`

**Interfaces:**
- Consumes: the `conn` fixture from `ui/tests/conftest.py` (writable in-memory DuckDB, schema applied, seeded with accounts 1/2/3, category 10 "Groceries", payee 100 "Store A", security 500 "Vanguard Total Stock Market Index", transactions up to id 3003 — see `conftest.py` for exact seed rows).
- Produces: `add_transaction(conn, account_id, txn_date, amount, memo=None, payee_name=None, category_name=None, security_name=None, activity=None, quantity=None, price=None) -> int` (returns the new `transaction_id`). This is what `ui/add_record_dialog.py` (Task 2) calls.

- [ ] **Step 1: Write the failing tests**

Create `ui/tests/test_writes.py`:

```python
from datetime import date
from decimal import Decimal

import pytest

import data
from writes import add_transaction


def test_add_transaction_inserts_plain_cash_row(conn):
    transaction_id = add_transaction(
        conn, account_id=1, txn_date=date(2024, 4, 1), amount=Decimal("-10.00"), memo="coffee",
    )
    row = conn.execute(
        "SELECT transaction_id, account_id, txn_date, amount, memo FROM transactions "
        "WHERE transaction_id = ?",
        [transaction_id],
    ).fetchone()
    assert row == (transaction_id, 1, date(2024, 4, 1), Decimal("-10.00"), "coffee")


def test_add_transaction_uses_max_id_plus_one(conn):
    # conn fixture seeds transaction_ids up to 3003 (see conftest.py).
    transaction_id = add_transaction(
        conn, account_id=1, txn_date=date(2024, 4, 1), amount=Decimal("5.00"),
    )
    assert transaction_id == 3004


def test_add_transaction_creates_new_payee_and_category(conn):
    transaction_id = add_transaction(
        conn, account_id=1, txn_date=date(2024, 4, 1), amount=Decimal("-9.00"),
        payee_name="New Cafe", category_name="Dining",
    )
    assert "New Cafe" in [name for _id, name in data.list_payees(conn)]
    assert "Dining" in [name for _id, name in data.list_categories(conn)]
    row = conn.execute(
        "SELECT p.name, c.name FROM transactions t "
        "JOIN payees p ON p.payee_id = t.payee_id "
        "JOIN categories c ON c.category_id = t.category_id "
        "WHERE t.transaction_id = ?",
        [transaction_id],
    ).fetchone()
    assert row == ("New Cafe", "Dining")


def test_add_transaction_reuses_existing_payee_case_insensitive(conn):
    before = len(data.list_payees(conn))
    add_transaction(
        conn, account_id=1, txn_date=date(2024, 4, 1), amount=Decimal("-1.00"),
        payee_name="store a",  # seeded payee is "Store A" (payee_id 100)
    )
    assert len(data.list_payees(conn)) == before
    row = conn.execute(
        "SELECT payee_id FROM transactions ORDER BY transaction_id DESC LIMIT 1"
    ).fetchone()
    assert row[0] == 100


def test_add_transaction_creates_new_security_for_investment(conn):
    transaction_id = add_transaction(
        conn, account_id=3, txn_date=date(2024, 4, 1), amount=Decimal("100.00"),
        security_name="New Fund", activity="1", quantity=Decimal("5.0"), price=Decimal("20.00"),
    )
    assert "New Fund" in [name for _id, name in data.list_securities(conn)]
    row = conn.execute(
        "SELECT sec.name, t.activity, t.quantity, t.price FROM transactions t "
        "JOIN securities sec ON sec.security_id = t.security_id "
        "WHERE t.transaction_id = ?",
        [transaction_id],
    ).fetchone()
    assert row == ("New Fund", "1", Decimal("5.0"), Decimal("20.00"))


def test_add_transaction_rolls_back_dictionary_inserts_on_failure(conn):
    before_payees = data.list_payees(conn)
    with pytest.raises(Exception):
        add_transaction(
            conn, account_id=1, txn_date=None, amount=Decimal("-1.00"),
            payee_name="Orphan Payee",
        )
    assert data.list_payees(conn) == before_payees
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest ui/tests/test_writes.py -v`
Expected: FAIL (or error) at collection — `ModuleNotFoundError: No module named 'writes'`.

- [ ] **Step 3: Write the implementation**

Create `ui/writes.py`:

```python
"""Write layer for the browsing UI: money.duckdb mutation lives only here.

data.py stays read-only/query-only (see its module docstring). Every insert
here runs inside one explicit transaction so a failed write can never leave
a dictionary row (payee/category/security) without the transaction that
introduced it, or vice versa.
"""


def _next_id(conn, table, id_column):
    # table/id_column are always literals from call sites in this module,
    # never user input, so this f-string is not an injection risk.
    row = conn.execute(f"SELECT MAX({id_column}) FROM {table}").fetchone()
    return (row[0] or 0) + 1


def _find_or_create(conn, table, id_column, name):
    row = conn.execute(
        f"SELECT {id_column} FROM {table} WHERE lower(name) = lower(?)", [name]
    ).fetchone()
    if row:
        return row[0]
    new_id = _next_id(conn, table, id_column)
    conn.execute(f"INSERT INTO {table} VALUES (?, ?)", [new_id, name])
    return new_id


def add_transaction(
    conn,
    account_id,
    txn_date,
    amount,
    memo=None,
    payee_name=None,
    category_name=None,
    security_name=None,
    activity=None,
    quantity=None,
    price=None,
):
    """Inserts a transaction row, auto-creating any named dictionary entry
    (payee/category/security) that doesn't already exist by name (case-
    insensitive). Returns the new transaction_id. Rolls back entirely (no
    partial dictionary rows) if the transaction insert itself fails."""
    conn.begin()
    try:
        payee_id = _find_or_create(conn, "payees", "payee_id", payee_name) if payee_name else None
        category_id = (
            _find_or_create(conn, "categories", "category_id", category_name)
            if category_name
            else None
        )
        security_id = (
            _find_or_create(conn, "securities", "security_id", security_name)
            if security_name
            else None
        )
        transaction_id = _next_id(conn, "transactions", "transaction_id")
        conn.execute(
            "INSERT INTO transactions VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                transaction_id, account_id, category_id, payee_id, txn_date, amount,
                memo, security_id, activity, quantity, price,
            ],
        )
    except Exception:
        conn.rollback()
        raise
    conn.commit()
    return transaction_id
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest ui/tests/test_writes.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add ui/writes.py ui/tests/test_writes.py
git commit -m "Add write layer for inserting transactions with dictionary auto-create"
```

---

### Task 2: Add Record dialog (`ui/add_record_dialog.py`)

**Files:**
- Create: `ui/add_record_dialog.py`
- Test: `ui/tests/test_add_record_dialog.py`

**Interfaces:**
- Consumes: `writes.add_transaction(...)` (Task 1); `data.list_payees(conn)`, `data.list_categories(conn)`, `data.list_securities(conn)` (existing, in `ui/data.py`); `data.INVESTMENT_ACCOUNT_TYPE`, `data.BUY_ACTIVITY`, `data.SELL_ACTIVITY` (existing constants).
- Produces: `AddRecordDialog(conn, account_id, account_type, parent=None)`, a `QDialog` subclass. After a successful `exec()` returning `QDialog.Accepted`, `dialog.transaction_id` holds the new transaction's id. This is what `ui/main_window.py` (Task 3) instantiates and calls `.exec()` on.

- [ ] **Step 1: Write the failing tests**

Create `ui/tests/test_add_record_dialog.py`:

```python
from decimal import Decimal

from PySide6.QtCore import QDate
from PySide6.QtWidgets import QDialog, QDialogButtonBox

from add_record_dialog import AddRecordDialog


def test_cash_account_has_payee_and_category_fields(qapp, conn):
    dialog = AddRecordDialog(conn, account_id=1, account_type="0", parent=None)
    assert hasattr(dialog, "payee_edit")
    assert hasattr(dialog, "category_edit")
    assert not hasattr(dialog, "security_edit")


def test_investment_account_has_security_and_activity_fields(qapp, conn):
    dialog = AddRecordDialog(conn, account_id=3, account_type="5", parent=None)
    assert hasattr(dialog, "security_edit")
    assert hasattr(dialog, "activity_combo")
    assert not hasattr(dialog, "payee_edit")


def test_ok_button_disabled_until_amount_is_valid(qapp, conn):
    dialog = AddRecordDialog(conn, account_id=1, account_type="0", parent=None)
    ok_button = dialog.button_box.button(QDialogButtonBox.Ok)
    assert not ok_button.isEnabled()
    dialog.amount_edit.setText("-12.50")
    assert ok_button.isEnabled()


def test_ok_button_disabled_for_investment_until_all_fields_valid(qapp, conn):
    dialog = AddRecordDialog(conn, account_id=3, account_type="5", parent=None)
    ok_button = dialog.button_box.button(QDialogButtonBox.Ok)
    dialog.amount_edit.setText("100.00")
    assert not ok_button.isEnabled()  # security/quantity/price still blank
    dialog.security_edit.setText("New Fund")
    dialog.quantity_edit.setText("5")
    dialog.price_edit.setText("20.00")
    assert ok_button.isEnabled()


def test_accept_adds_transaction_and_closes_dialog(qapp, conn):
    dialog = AddRecordDialog(conn, account_id=1, account_type="0", parent=None)
    dialog.date_edit.setDate(QDate(2024, 4, 1))
    dialog.amount_edit.setText("-9.00")
    dialog.payee_edit.setText("New Cafe")
    dialog.category_edit.setText("Dining")

    dialog._on_accept()

    assert dialog.result() == QDialog.Accepted
    assert dialog.transaction_id is not None
    row = conn.execute(
        "SELECT amount FROM transactions WHERE transaction_id = ?", [dialog.transaction_id]
    ).fetchone()
    assert row == (Decimal("-9.00"),)


def test_write_failure_shows_error_and_keeps_dialog_open(qapp, conn, monkeypatch):
    import writes

    def failing_add_transaction(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(writes, "add_transaction", failing_add_transaction)

    dialog = AddRecordDialog(conn, account_id=1, account_type="0", parent=None)
    dialog.amount_edit.setText("-9.00")

    dialog._on_accept()

    assert dialog.result() != QDialog.Accepted
    assert "boom" in dialog.error_label.text()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest ui/tests/test_add_record_dialog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'add_record_dialog'`.

- [ ] **Step 3: Write the implementation**

Create `ui/add_record_dialog.py`:

```python
"""Modal dialog for adding a new transaction to an account."""

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

import data
import writes
from data import BUY_ACTIVITY, INVESTMENT_ACCOUNT_TYPE, SELL_ACTIVITY

ACTIVITY_CHOICES = [("Buy", BUY_ACTIVITY), ("Sell", SELL_ACTIVITY)]


def _make_completer(names):
    completer = QCompleter(names)
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    completer.setFilterMode(Qt.MatchContains)
    return completer


def _parse_decimal(text):
    text = text.strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


class AddRecordDialog(QDialog):
    """Add a transaction to `account_id`. Cash accounts get Payee/Category
    fields; investment accounts (account_type == INVESTMENT_ACCOUNT_TYPE)
    get Security/Activity/Quantity/Price fields instead."""

    def __init__(self, conn, account_id, account_type, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._account_id = account_id
        self._is_investment = account_type == INVESTMENT_ACCOUNT_TYPE
        self.transaction_id = None

        self.setWindowTitle("Add Record")

        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)

        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("e.g. -52.30")

        self.memo_edit = QLineEdit()

        form = QFormLayout()
        form.addRow("Date:", self.date_edit)

        if self._is_investment:
            self.security_edit = QLineEdit()
            self.security_edit.setCompleter(_make_completer(self._dictionary_names(data.list_securities)))
            self.activity_combo = QComboBox()
            for label, code in ACTIVITY_CHOICES:
                self.activity_combo.addItem(label, code)
            self.quantity_edit = QLineEdit()
            self.price_edit = QLineEdit()
            form.addRow("Security:", self.security_edit)
            form.addRow("Activity:", self.activity_combo)
            form.addRow("Quantity:", self.quantity_edit)
            form.addRow("Price:", self.price_edit)
        else:
            self.payee_edit = QLineEdit()
            self.payee_edit.setCompleter(_make_completer(self._dictionary_names(data.list_payees)))
            self.category_edit = QLineEdit()
            self.category_edit.setCompleter(_make_completer(self._dictionary_names(data.list_categories)))
            form.addRow("Payee:", self.payee_edit)
            form.addRow("Category:", self.category_edit)

        form.addRow("Amount:", self.amount_edit)
        form.addRow("Memo:", self.memo_edit)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        self.error_label.setWordWrap(True)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addWidget(self.button_box)

        self.amount_edit.textChanged.connect(self._validate)
        if self._is_investment:
            self.security_edit.textChanged.connect(self._validate)
            self.quantity_edit.textChanged.connect(self._validate)
            self.price_edit.textChanged.connect(self._validate)

        self._validate()

    def _dictionary_names(self, list_fn):
        try:
            return [name for _id, name in list_fn(self._conn)]
        except Exception:
            return []

    def _validate(self):
        valid = _parse_decimal(self.amount_edit.text()) is not None
        if self._is_investment:
            valid = (
                valid
                and bool(self.security_edit.text().strip())
                and _parse_decimal(self.quantity_edit.text()) is not None
                and _parse_decimal(self.price_edit.text()) is not None
            )
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(valid)

    def _on_accept(self):
        amount = _parse_decimal(self.amount_edit.text())
        memo = self.memo_edit.text().strip() or None
        if self._is_investment:
            kwargs = dict(
                security_name=self.security_edit.text().strip() or None,
                activity=self.activity_combo.currentData(),
                quantity=_parse_decimal(self.quantity_edit.text()),
                price=_parse_decimal(self.price_edit.text()),
            )
        else:
            kwargs = dict(
                payee_name=self.payee_edit.text().strip() or None,
                category_name=self.category_edit.text().strip() or None,
            )

        try:
            self.transaction_id = writes.add_transaction(
                self._conn,
                self._account_id,
                self.date_edit.date().toPython(),
                amount,
                memo=memo,
                **kwargs,
            )
        except Exception as exc:
            self.error_label.setText(f"Failed to add record: {exc}")
            return
        self.accept()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest ui/tests/test_add_record_dialog.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add ui/add_record_dialog.py ui/tests/test_add_record_dialog.py
git commit -m "Add AddRecordDialog for entering a new transaction"
```

---

### Task 3: Wire "Add Record" into the main window

**Files:**
- Modify: `ui/main_window.py:204-231` (`_install_row_action_buttons`), and add a new handler method near `_on_value_button_clicked` (`ui/main_window.py:257-273`)
- Test: `ui/tests/test_main_window.py`

**Interfaces:**
- Consumes: `AddRecordDialog` (Task 2); existing `self.account_model.account_at(row)`, `self._reload_accounts()`, `self.account_view.selectRow(row)`, `self._on_account_selected()` (all already in `main_window.py`).
- Produces: nothing new consumed elsewhere — this is the UI entry point.

- [ ] **Step 1: Write the failing tests**

Add to `ui/tests/test_main_window.py`:

```python
from PySide6.QtWidgets import QDialog, QPushButton

from main_window import MainWindow


def test_account_rows_have_add_record_button(qapp, conn):
    window = MainWindow(conn)
    actions_col = window.account_model.COLUMNS.index("Actions")
    container = window.account_view.indexWidget(window.account_model.index(0, actions_col))
    button_texts = [child.text() for child in container.findChildren(QPushButton)]
    assert "Add Record" in button_texts


def test_add_record_button_reloads_account_on_accept(qapp, conn, monkeypatch):
    import add_record_dialog

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)
    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", lambda self: QDialog.Accepted)

    window = MainWindow(conn)
    reload_calls.clear()  # drop the reload that happened during __init__

    window._on_add_record_button_clicked(1)  # row 1 = Checking (cash account, see conn fixture ordering)

    assert reload_calls == [True]
    assert window.statusBar().currentMessage() == "Record added."


def test_add_record_button_does_nothing_on_cancel(qapp, conn, monkeypatch):
    import add_record_dialog

    reload_calls = []
    original_reload = MainWindow._reload_accounts

    def spy_reload(self):
        reload_calls.append(True)
        original_reload(self)

    monkeypatch.setattr(MainWindow, "_reload_accounts", spy_reload)
    monkeypatch.setattr(add_record_dialog.AddRecordDialog, "exec", lambda self: QDialog.Rejected)

    window = MainWindow(conn)
    reload_calls.clear()

    window._on_add_record_button_clicked(1)

    assert reload_calls == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest ui/tests/test_main_window.py -v`
Expected: FAIL — `AttributeError: 'MainWindow' object has no attribute '_on_add_record_button_clicked'` (and the button-existence test fails since the button doesn't exist yet).

- [ ] **Step 3: Write the implementation**

In `ui/main_window.py`, add the import near the other local imports (after the `table_copy` import at line 38):

```python
from add_record_dialog import AddRecordDialog
```

In `_install_row_action_buttons` (`ui/main_window.py:204-231`), add a fourth button after the `value_button` block (i.e., right before `self.account_view.setIndexWidget(...)`):

```python
            add_record_button = QPushButton("Add Record")
            add_record_button.setStyleSheet(ROW_BUTTON_STYLE)
            add_record_button.clicked.connect(partial(self._on_add_record_button_clicked, row))
            layout.addWidget(add_record_button)
```

Add a new method after `_on_value_button_clicked` (`ui/main_window.py:257-273`):

```python
    def _on_add_record_button_clicked(self, row):
        account_id, _name, account_type, _currency, _balance, _is_closed = self.account_model.account_at(
            row
        )
        dialog = AddRecordDialog(self._conn, account_id, account_type, parent=self)
        if dialog.exec() != AddRecordDialog.Accepted:
            return
        self._reload_accounts()
        self.account_view.selectRow(row)
        self._on_account_selected()
        self.statusBar().showMessage("Record added.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest ui/tests/test_main_window.py -v`
Expected: all passed (existing + 3 new tests).

- [ ] **Step 5: Commit**

```bash
git add ui/main_window.py ui/tests/test_main_window.py
git commit -m "Wire Add Record button into account row actions"
```

---

### Task 4: Make the app connection writable, update docs, full regression run

**Files:**
- Modify: `ui/main.py:27`
- Modify: `README.md` (the "Browsing the data" section)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new — this is the last task, wiring the real DB connection and documenting the feature.

- [ ] **Step 1: Drop the read-only flag**

In `ui/main.py:27`, change:

```python
    conn = duckdb.connect(str(DB_PATH), read_only=True)
```

to:

```python
    conn = duckdb.connect(str(DB_PATH))
```

- [ ] **Step 2: Update README.md**

In `README.md`, replace this paragraph (in the "Browsing the data" section):

```markdown
Opens a desktop window (PySide6) listing accounts on the left; selecting
one shows its transactions on the right. Closed accounts are hidden by
default — check "Show closed accounts" to see them. Read-only: this tool
does not modify money.duckdb. Requires `money.duckdb` to already exist
(run `./extract-data-to-db.sh` first if it doesn't).
```

with:

```markdown
Opens a desktop window (PySide6) listing accounts on the left; selecting
one shows its transactions on the right. Closed accounts are hidden by
default — check "Show closed accounts" to see them. Requires
`money.duckdb` to already exist (run `./extract-data-to-db.sh` first if it
doesn't).

Each account row has an "Add Record" button that opens a form for adding a
single transaction to that account (Payee/Category for cash accounts;
Security/Activity/Quantity/Price for investment accounts). Typing a new
Payee, Category, or Security name adds it to the corresponding dictionary
automatically; existing names autocomplete as you type. This is the only
place the app writes to `money.duckdb` — everything else remains
read-only. Note: re-running `./extract-data-to-db.sh` rebuilds
`money.duckdb` from the `.mny` file from scratch, so manually-added
records won't survive a re-extraction.
```

- [ ] **Step 3: Run the full test suite**

Run: `.venv/bin/pytest ui/tests/ etl/tests/ -v`
Expected: all tests pass (no regressions from the connection change; `ui/tests/conftest.py`'s `conn`/`dict_conn` fixtures already connect without `read_only`, so this change only affects `ui/main.py`, which has no direct test coverage).

- [ ] **Step 4: Manual verification**

Run: `./run-ui.sh`
- Select a cash account, click "Add Record", enter a date/amount and a brand-new payee/category name, click OK. Confirm the new row appears in the transaction table and the account balance updates.
- Open the Dictionaries tab and confirm the new payee/category name is listed there.
- Select an investment account, click "Add Record", enter a brand-new security name with Buy activity/quantity/price, click OK. Confirm the row appears and the new security shows up in Dictionaries > Investments.
- Click "Add Record" again and confirm the Payee/Category (or Security) fields autocomplete against the names just added.

- [ ] **Step 5: Commit**

```bash
git add ui/main.py README.md
git commit -m "Make the UI's database connection writable and document Add Record"
```
