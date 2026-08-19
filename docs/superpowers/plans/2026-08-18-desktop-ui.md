# Desktop UI for Browsing Extracted Money Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a read-only PySide6 desktop app that lists accounts and shows a selected account's transactions, reading from the existing `money.duckdb`.

**Architecture:** A new `ui/` package with a DuckDB query layer (`data.py`) separated from Qt widgets (`models.py`, `main_window.py`, `main.py`), following the same data/IO separation `etl/` already uses. No caching, no background threads — queries are cheap enough to run synchronously on the GUI thread.

**Tech Stack:** Python 3 (existing project `.venv`), PySide6 (Qt6 bindings), DuckDB (existing `duckdb` package), pytest.

**Spec:** `docs/superpowers/specs/2026-08-18-desktop-ui-design.md`

## Global Constraints

- Read-only: the UI opens `money.duckdb` with `read_only=True`; no write/insert/update statements anywhere in this plan.
- Closed accounts are excluded from `list_accounts` unless `include_closed=True` is passed explicitly.
- All Python code lives in `ui/`, using the project's existing root-level `.venv` (not a separate one).
- `data.py` functions take an already-open `duckdb.DuckDBPyConnection` and return plain tuples — no Qt types in that module, so it stays testable without a `QApplication`.
- The account list is sorted by `name` ascending; transactions are sorted by `txn_date` descending (most recent first).

---

## Task 1: DuckDB query layer

**Files:**
- Create: `ui/data.py`
- Create: `ui/tests/conftest.py`
- Create: `ui/tests/test_data.py`

**Interfaces:**
- Produces:
  - `list_accounts(conn: duckdb.DuckDBPyConnection, include_closed: bool = False) -> list[tuple[int, str, str | None]]` — rows of `(account_id, name, account_type)`, sorted by `name` ascending, excluding `is_closed = TRUE` rows unless `include_closed=True`.
  - `list_transactions(conn: duckdb.DuckDBPyConnection, account_id: int) -> list[tuple[int, date, str | None, str | None, str | None, Decimal]]` — rows of `(transaction_id, txn_date, payee_name, category_name, memo, amount)` for the given account, `payee_name`/`category_name` are `None` when the transaction has no payee/category, sorted by `txn_date` descending.

- [ ] **Step 1: Write the fixture conftest**

Reuses `etl/schema.py`'s `apply_schema` so the test schema can't drift from the real one, then seeds two accounts (one open, one closed), one category, one payee, and two transactions (one with payee/category set, one with both null) for the joins/null tests below.

```python
# ui/tests/conftest.py
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "etl"))

import duckdb
import pytest

from schema import apply_schema


@pytest.fixture
def conn():
    connection = duckdb.connect(":memory:")
    apply_schema(connection)
    connection.execute(
        "INSERT INTO accounts VALUES "
        "(1, 'Checking', 'Bank', FALSE), "
        "(2, 'Old Card', 'Credit', TRUE)"
    )
    connection.execute("INSERT INTO categories VALUES (10, 'Groceries')")
    connection.execute("INSERT INTO payees VALUES (100, 'Store A')")
    connection.execute(
        "INSERT INTO transactions VALUES "
        "(1000, 1, 10, 100, '2024-03-15', -52.30, 'weekly shop'), "
        "(1001, 1, NULL, NULL, '2024-03-10', 1000.00, NULL)"
    )
    yield connection
    connection.close()
```

- [ ] **Step 2: Write the failing tests**

```python
# ui/tests/test_data.py
from datetime import date
from decimal import Decimal

from data import list_accounts, list_transactions


def test_list_accounts_excludes_closed_by_default(conn):
    assert list_accounts(conn) == [(1, "Checking", "Bank")]


def test_list_accounts_includes_closed_when_requested(conn):
    assert list_accounts(conn, include_closed=True) == [
        (1, "Checking", "Bank"),
        (2, "Old Card", "Credit"),
    ]


def test_list_transactions_returns_joined_rows_sorted_by_date_desc(conn):
    transactions = list_transactions(conn, account_id=1)
    assert transactions == [
        (1000, date(2024, 3, 15), "Store A", "Groceries", "weekly shop", Decimal("-52.30")),
        (1001, date(2024, 3, 10), None, None, None, Decimal("1000.00")),
    ]


def test_list_transactions_unknown_account_returns_empty(conn):
    assert list_transactions(conn, account_id=999) == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest ui/tests/test_data.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'data'` (or `ImportError`), since `ui/data.py` doesn't exist yet.

- [ ] **Step 4: Implement the query layer**

```python
# ui/data.py
"""DuckDB query layer for the browsing UI. Read-only: no writes here."""

import duckdb


def list_accounts(
    conn: duckdb.DuckDBPyConnection, include_closed: bool = False
) -> list[tuple]:
    query = "SELECT account_id, name, account_type FROM accounts"
    if not include_closed:
        query += " WHERE is_closed = FALSE"
    query += " ORDER BY name"
    return conn.execute(query).fetchall()


def list_transactions(conn: duckdb.DuckDBPyConnection, account_id: int) -> list[tuple]:
    query = """
        SELECT t.transaction_id, t.txn_date, p.name, c.name, t.memo, t.amount
        FROM transactions t
        LEFT JOIN payees p ON t.payee_id = p.payee_id
        LEFT JOIN categories c ON t.category_id = c.category_id
        WHERE t.account_id = ?
        ORDER BY t.txn_date DESC
    """
    return conn.execute(query, [account_id]).fetchall()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest ui/tests/test_data.py -v`
Expected: 4 passed

- [ ] **Step 6: Commit**

```bash
git add ui/data.py ui/tests/conftest.py ui/tests/test_data.py
git commit -m "Add DuckDB query layer for the browsing UI"
```

---

## Task 2: Qt table models

**Files:**
- Create: `ui/requirements.txt`
- Create: `ui/models.py`

**Interfaces:**
- Consumes: the row shapes produced by `list_accounts` and `list_transactions` (Task 1) — `AccountTableModel` expects `(account_id, name, account_type)` tuples, `TransactionTableModel` expects `(transaction_id, txn_date, payee_name, category_name, memo, amount)` tuples.
- Produces:
  - `AccountTableModel(accounts: list | None = None, parent=None)` — `QAbstractTableModel` subclass. Columns: `["Name", "Type"]`. Methods: `set_accounts(accounts)` (replaces data, emits reset), `account_id_at(row: int) -> int`.
  - `TransactionTableModel(transactions: list | None = None, parent=None)` — `QAbstractTableModel` subclass. Columns: `["Date", "Payee", "Category", "Memo", "Amount"]`. Method: `set_transactions(transactions)` (replaces data, emits reset).

- [ ] **Step 1: Add the PySide6 dependency**

```
# ui/requirements.txt
PySide6>=6.7
```

- [ ] **Step 2: Install it into the project venv**

Run: `.venv/bin/pip install -q -r ui/requirements.txt`
Expected: installs without error (venv already exists from the ETL stage).

- [ ] **Step 3: Implement the table models**

```python
# ui/models.py
"""Qt table models adapting data.py query results for QTableViews."""

from PySide6.QtCore import QAbstractTableModel, Qt


class AccountTableModel(QAbstractTableModel):
    COLUMNS = ["Name", "Type"]

    def __init__(self, accounts=None, parent=None):
        super().__init__(parent)
        self._accounts = accounts or []

    def set_accounts(self, accounts):
        self.beginResetModel()
        self._accounts = accounts
        self.endResetModel()

    def account_id_at(self, row):
        return self._accounts[row][0]

    def rowCount(self, parent=None):
        return len(self._accounts)

    def columnCount(self, parent=None):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        _, name, account_type = self._accounts[index.row()]
        return [name, account_type or ""][index.column()]


class TransactionTableModel(QAbstractTableModel):
    COLUMNS = ["Date", "Payee", "Category", "Memo", "Amount"]

    def __init__(self, transactions=None, parent=None):
        super().__init__(parent)
        self._transactions = transactions or []

    def set_transactions(self, transactions):
        self.beginResetModel()
        self._transactions = transactions
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self._transactions)

    def columnCount(self, parent=None):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        _, txn_date, payee, category, memo, amount = self._transactions[index.row()]
        values = [
            txn_date.isoformat(),
            payee or "",
            category or "",
            memo or "",
            f"{amount:.2f}",
        ]
        return values[index.column()]
```

- [ ] **Step 4: Manually verify the models (no display needed)**

Run (offscreen Qt platform, no display required):

```bash
QT_QPA_PLATFORM=offscreen .venv/bin/python -c "
from datetime import date
from decimal import Decimal

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt

app = QApplication([])

import sys
sys.path.insert(0, 'ui')
from models import AccountTableModel, TransactionTableModel

am = AccountTableModel([(1, 'Checking', 'Bank')])
assert am.rowCount() == 1
assert am.columnCount() == 2
assert am.data(am.index(0, 0)) == 'Checking'
assert am.data(am.index(0, 1)) == 'Bank'
assert am.account_id_at(0) == 1

tm = TransactionTableModel([(1000, date(2024, 3, 15), None, None, None, Decimal('-52.30'))])
assert tm.rowCount() == 1
assert tm.data(tm.index(0, 0)) == '2024-03-15'
assert tm.data(tm.index(0, 1)) == ''
assert tm.data(tm.index(0, 4)) == '-52.30'

print('OK')
"
```

Expected output: `OK`

- [ ] **Step 5: Commit**

```bash
git add ui/requirements.txt ui/models.py
git commit -m "Add Qt table models for accounts and transactions"
```

---

## Task 3: Main window, entry point, and launcher

**Files:**
- Create: `ui/main_window.py`
- Create: `ui/main.py`
- Create: `run-ui.sh`
- Modify: `README.md` (add a "Browsing the data" section)

**Interfaces:**
- Consumes:
  - `data.list_accounts(conn, include_closed=False)`, `data.list_transactions(conn, account_id)` (Task 1)
  - `models.AccountTableModel`, `models.TransactionTableModel`, including `set_accounts`, `set_transactions`, `account_id_at` (Task 2)
- Produces:
  - `main_window.MainWindow(conn: duckdb.DuckDBPyConnection, parent=None)` — `QMainWindow` subclass, ready to `.show()`.
  - `main.main()` — resolves the DB path, opens it read-only, builds and shows `MainWindow`, runs the Qt event loop.

- [ ] **Step 1: Implement the main window**

```python
# ui/main_window.py
"""Main window: account list (left) + transaction table (right)."""

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QMainWindow,
    QTableView,
    QVBoxLayout,
    QWidget,
)

import data
from models import AccountTableModel, TransactionTableModel


class MainWindow(QMainWindow):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setWindowTitle("Money Browser")
        self.resize(1000, 600)

        self.account_model = AccountTableModel()
        self.transaction_model = TransactionTableModel()

        self.show_closed_checkbox = QCheckBox("Show closed accounts")
        self.show_closed_checkbox.stateChanged.connect(self._reload_accounts)

        self.account_view = QTableView()
        self.account_view.setModel(self.account_model)
        self.account_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.account_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.account_view.selectionModel().selectionChanged.connect(self._on_account_selected)

        self.transaction_view = QTableView()
        self.transaction_view.setModel(self.transaction_model)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.show_closed_checkbox)
        left_layout.addWidget(self.account_view)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(left, 1)
        layout.addWidget(self.transaction_view, 2)
        self.setCentralWidget(central)

        self._reload_accounts()

    def _reload_accounts(self):
        include_closed = self.show_closed_checkbox.isChecked()
        try:
            accounts = data.list_accounts(self._conn, include_closed=include_closed)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to load accounts: {exc}")
            return
        self.account_model.set_accounts(accounts)
        self.transaction_model.set_transactions([])

    def _on_account_selected(self, selected=None, deselected=None):
        indexes = self.account_view.selectionModel().selectedRows()
        if not indexes:
            self.transaction_model.set_transactions([])
            return
        account_id = self.account_model.account_id_at(indexes[0].row())
        try:
            transactions = data.list_transactions(self._conn, account_id)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to load transactions: {exc}")
            return
        self.transaction_model.set_transactions(transactions)
```

- [ ] **Step 2: Implement the entry point**

```python
# ui/main.py
"""Entry point for the Money Browser desktop UI."""

import sys
from pathlib import Path

import duckdb
from PySide6.QtWidgets import QApplication, QMessageBox

sys.path.insert(0, str(Path(__file__).resolve().parent))
from main_window import MainWindow

DB_PATH = Path(__file__).resolve().parent.parent / "money.duckdb"


def main():
    app = QApplication(sys.argv)

    if not DB_PATH.exists():
        QMessageBox.critical(
            None,
            "Money Browser",
            f"No database found at {DB_PATH}.\n"
            'Run ./extract-data-to-db.sh "<file.mny>" first.',
        )
        sys.exit(1)

    conn = duckdb.connect(str(DB_PATH), read_only=True)
    window = MainWindow(conn)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Add the launcher script**

```bash
#!/usr/bin/env bash
# run-ui.sh
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$ROOT_DIR/.venv"

if [ ! -d "$VENV_DIR" ]; then
    python3 -m venv "$VENV_DIR"
fi
"$VENV_DIR/bin/pip" install -q -r "$ROOT_DIR/etl/requirements.txt" -r "$ROOT_DIR/ui/requirements.txt"
"$VENV_DIR/bin/python" "$ROOT_DIR/ui/main.py"
```

Run: `chmod +x run-ui.sh`

- [ ] **Step 4: Document it in the README**

Add this section after the existing "## Querying the result" section in `README.md`:

```markdown
## Browsing the data

    ./run-ui.sh

Opens a desktop window (PySide6) listing accounts on the left; selecting
one shows its transactions on the right. Closed accounts are hidden by
default — check "Show closed accounts" to see them. Read-only: this tool
does not modify `money.duckdb`. Requires `money.duckdb` to already exist
(run `./extract-data-to-db.sh` first if it doesn't).
```

- [ ] **Step 5: Manually verify the full app against the real database**

Run: `./run-ui.sh`
Expected: a window titled "Money Browser" opens, the left pane lists open accounts sorted by name, selecting an account populates the right pane with that account's transactions sorted newest-first, and checking "Show closed accounts" adds closed accounts to the list. Close the window when done.

- [ ] **Step 6: Commit**

```bash
git add ui/main_window.py ui/main.py run-ui.sh README.md
git commit -m "Add main window, entry point, and launcher for the browsing UI"
```
