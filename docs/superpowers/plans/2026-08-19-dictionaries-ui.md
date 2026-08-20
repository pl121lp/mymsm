# Dictionaries Browsing UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Dictionaries" tab to the Money Browser UI where the user can browse categories (list of all their transactions across accounts) and investments/securities (price and cumulative-holdings charts over time, per account).

**Architecture:** Extend the existing `ui/` package's `data.py`/`models.py`/widget split. Four new read-only query functions in `data.py`, two new Qt models in `models.py`, a new `ui/dictionaries_tab.py` widget file owning the two sub-tabs (Categories, Investments), and `main_window.py` wraps its existing splitter plus the new tab in a top-level `QTabWidget`.

**Tech Stack:** Python, PySide6 (including `PySide6.QtCharts`, already installed — no new dependency), DuckDB, pytest.

**Spec:** `docs/superpowers/specs/2026-08-19-dictionaries-ui-design.md`

## Global Constraints

- Read-only: no write/INSERT/UPDATE operations anywhere in this feature.
- No new dependencies — `PySide6.QtCharts` ships with the already-installed `PySide6` package.
- Follow the existing `data.py` (plain Python types, no Qt) / `models.py` (`QAbstractTableModel`/`QAbstractListModel` subclasses) / widget-file split.
- `data.py` functions and `models.py` classes get `pytest` coverage with exact expected-value assertions (existing repo convention). Widget/chart wiring in `dictionaries_tab.py` and `main_window.py` is **not** covered by automated tests — verified by manually running the app, consistent with the existing convention for `main_window.py`.
- Investment quantity-over-time is a cumulative running total using buy/sell-only logic (activity codes `"1"`/`"2"`), matching `data.py`'s existing `BUY_ACTIVITY`/`SELL_ACTIVITY` constants and the account-valuation logic in `list_accounts`.
- Investment charts show one series per account (per-account breakdown, not aggregated).

---

### Task 1: Data layer — category dictionary queries

**Files:**
- Modify: `ui/data.py`
- Modify: `ui/tests/conftest.py` (add a new fixture, `dict_conn`, alongside the existing `conn` fixture — do not change `conn`, since existing tests assert exact-equality lists against its current seed data)
- Test: `ui/tests/test_data.py`

**Interfaces:**
- Produces: `data.list_categories(conn) -> list[tuple[int, str]]` — `(category_id, name)`, ordered by name.
- Produces: `data.list_category_transactions(conn, category_id) -> list[tuple]` — `(transaction_id, txn_date, account_name, payee, memo, amount)`, ordered by `txn_date` descending.
- Produces (fixture): `dict_conn` — an in-memory DuckDB connection seeded with 2 categories, 2 non-investment accounts, 2 investment accounts, 2 securities, and transactions covering both category-tagging-across-accounts and per-account investment history. Task 2 also uses this fixture.

- [ ] **Step 1: Add the `dict_conn` fixture**

Add to `ui/tests/conftest.py` (below the existing `conn` fixture, same file, same imports already present):

```python
@pytest.fixture
def dict_conn():
    connection = duckdb.connect(":memory:")
    apply_schema(connection)
    connection.execute(
        "INSERT INTO accounts VALUES "
        "(1, 'Checking', 'Bank', FALSE, 0.00, 'USD'), "
        "(2, 'Savings', 'Bank', FALSE, 0.00, 'USD'), "
        "(3, 'Brokerage A', '5', FALSE, 0.00, 'USD'), "
        "(4, 'Brokerage B', '5', FALSE, 0.00, 'USD')"
    )
    connection.execute(
        "INSERT INTO categories VALUES (10, 'Utilities'), (20, 'Groceries')"
    )
    connection.execute(
        "INSERT INTO payees VALUES (100, 'Store A'), (101, 'Store B')"
    )
    connection.execute(
        "INSERT INTO securities VALUES "
        "(500, 'Vanguard Total Stock Market Index'), (501, 'Apple Inc')"
    )
    connection.execute(
        "INSERT INTO transactions VALUES "
        "(1000, 1, 20, 100, '2024-03-15', -52.30, 'weekly shop', NULL, NULL, NULL, NULL), "
        "(1001, 2, 20, 101, '2024-03-10', -20.00, 'snacks', NULL, NULL, NULL, NULL), "
        "(1002, 1, 10, NULL, '2024-03-01', -75.00, 'electric bill', NULL, NULL, NULL, NULL), "
        "(3000, 3, NULL, NULL, '2024-01-10', 147.12, NULL, 500, '1', 8.0, 18.39), "
        "(3001, 3, NULL, NULL, '2024-02-10', 64.62, NULL, 500, '1', 3.0, 21.54), "
        "(3002, 3, NULL, NULL, '2024-03-01', -22.63, NULL, 500, '2', 1.0, 22.63), "
        "(4000, 4, NULL, NULL, '2024-01-15', 200.00, NULL, 500, '1', 10.0, 20.00), "
        "(4001, 4, NULL, NULL, '2024-02-20', -50.00, NULL, 500, '2', 2.0, 25.00)"
    )
    yield connection
    connection.close()
```

- [ ] **Step 2: Write the failing tests**

Add to `ui/tests/test_data.py`:

```python
from data import list_categories, list_category_transactions


def test_list_categories_returns_all_ordered_by_name(dict_conn):
    assert list_categories(dict_conn) == [
        (20, "Groceries"),
        (10, "Utilities"),
    ]


def test_list_category_transactions_returns_rows_across_accounts_sorted_by_date_desc(dict_conn):
    assert list_category_transactions(dict_conn, category_id=20) == [
        (1000, date(2024, 3, 15), "Checking", "Store A", "weekly shop", Decimal("-52.30")),
        (1001, date(2024, 3, 10), "Savings", "Store B", "snacks", Decimal("-20.00")),
    ]


def test_list_category_transactions_unknown_category_returns_empty(dict_conn):
    assert list_category_transactions(dict_conn, category_id=999) == []
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_data.py -k category -v`
Expected: FAIL with `ImportError: cannot import name 'list_categories'`

- [ ] **Step 4: Implement the two functions**

Add to `ui/data.py` (below the existing `list_transactions` function):

```python
def list_categories(conn: duckdb.DuckDBPyConnection) -> list[tuple]:
    return conn.execute(
        "SELECT category_id, name FROM categories ORDER BY name"
    ).fetchall()


def list_category_transactions(
    conn: duckdb.DuckDBPyConnection, category_id: int
) -> list[tuple]:
    query = """
        SELECT t.transaction_id, t.txn_date, a.name, p.name, t.memo, t.amount
        FROM transactions t
        JOIN accounts a ON a.account_id = t.account_id
        LEFT JOIN payees p ON t.payee_id = p.payee_id
        WHERE t.category_id = ?
        ORDER BY t.txn_date DESC
    """
    return conn.execute(query, [category_id]).fetchall()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_data.py -k category -v`
Expected: PASS (3 tests)

- [ ] **Step 6: Run the full test suite to confirm no regressions**

Run: `cd ui && ../.venv/bin/python -m pytest tests/ -v`
Expected: PASS, same count as before plus 3 new passes; no existing test changed behavior.

- [ ] **Step 7: Commit**

```bash
git add ui/data.py ui/tests/conftest.py ui/tests/test_data.py
git commit -m "Add category dictionary queries (list_categories, list_category_transactions)"
```

---

### Task 2: Data layer — investment dictionary queries

**Files:**
- Modify: `ui/data.py`
- Test: `ui/tests/test_data.py`

**Interfaces:**
- Consumes: `dict_conn` fixture from Task 1 (`ui/tests/conftest.py`).
- Consumes: `BUY_ACTIVITY`, `SELL_ACTIVITY` module constants already defined at the top of `ui/data.py`.
- Produces: `data.list_securities(conn) -> list[tuple[int, str]]` — `(security_id, name)`, ordered by name.
- Produces: `data.list_security_history(conn, security_id) -> list[tuple]` — `(account_id, account_name, txn_date, price, cumulative_qty)`, one row per Buy/Sell transaction, ordered by account name then date, `cumulative_qty` a running signed total per account (Sell negates, matching `list_accounts`'s existing `signed_qty` logic).

- [ ] **Step 1: Write the failing tests**

Add to `ui/tests/test_data.py`:

```python
from data import list_securities, list_security_history


def test_list_securities_returns_all_ordered_by_name(dict_conn):
    assert list_securities(dict_conn) == [
        (501, "Apple Inc"),
        (500, "Vanguard Total Stock Market Index"),
    ]


def test_list_security_history_computes_per_account_running_total(dict_conn):
    assert list_security_history(dict_conn, security_id=500) == [
        (3, "Brokerage A", date(2024, 1, 10), Decimal("18.39"), Decimal("8.0")),
        (3, "Brokerage A", date(2024, 2, 10), Decimal("21.54"), Decimal("11.0")),
        (3, "Brokerage A", date(2024, 3, 1), Decimal("22.63"), Decimal("10.0")),
        (4, "Brokerage B", date(2024, 1, 15), Decimal("20.00"), Decimal("10.0")),
        (4, "Brokerage B", date(2024, 2, 20), Decimal("25.00"), Decimal("8.0")),
    ]


def test_list_security_history_unknown_security_returns_empty(dict_conn):
    assert list_security_history(dict_conn, security_id=999) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_data.py -k security -v`
Expected: FAIL with `ImportError: cannot import name 'list_securities'`

- [ ] **Step 3: Implement the two functions**

Add to `ui/data.py`:

```python
def list_securities(conn: duckdb.DuckDBPyConnection) -> list[tuple]:
    return conn.execute(
        "SELECT security_id, name FROM securities ORDER BY name"
    ).fetchall()


def list_security_history(
    conn: duckdb.DuckDBPyConnection, security_id: int
) -> list[tuple]:
    query = """
        WITH signed AS (
            SELECT t.transaction_id, t.account_id, a.name AS account_name,
                   t.txn_date, t.price,
                   CASE WHEN t.activity = ? THEN -t.quantity ELSE t.quantity END AS signed_qty
            FROM transactions t
            JOIN accounts a ON a.account_id = t.account_id
            WHERE t.security_id = ? AND t.activity IN (?, ?)
        )
        SELECT account_id, account_name, txn_date, price,
               SUM(signed_qty) OVER (
                   PARTITION BY account_id
                   ORDER BY txn_date, transaction_id
                   ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
               ) AS cumulative_qty
        FROM signed
        ORDER BY account_name, txn_date, transaction_id
    """
    params = [SELL_ACTIVITY, security_id, BUY_ACTIVITY, SELL_ACTIVITY]
    return conn.execute(query, params).fetchall()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_data.py -k security -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `cd ui && ../.venv/bin/python -m pytest tests/ -v`
Expected: PASS, all tests including the 6 new ones from Tasks 1 and 2.

- [ ] **Step 6: Commit**

```bash
git add ui/data.py ui/tests/test_data.py
git commit -m "Add investment dictionary queries (list_securities, list_security_history)"
```

---

### Task 3: Model — DictionaryListModel

**Files:**
- Modify: `ui/models.py`
- Test: `ui/tests/test_models.py`

**Interfaces:**
- Produces: `models.DictionaryListModel(items=None, parent=None)` — a `QAbstractListModel` wrapping a list of `(id, name)` tuples.
  - `.set_items(items)` — resets the model with a new list.
  - `.id_at(row) -> int` — returns the id at that row.
  - `.data(index, role)` — returns `name` for `Qt.DisplayRole`.
  - `.rowCount(parent=None) -> int`

- [ ] **Step 1: Write the failing tests**

Add to `ui/tests/test_models.py`:

```python
from PySide6.QtCore import QAbstractListModel

from models import DictionaryListModel


def test_dictionary_list_model_shows_name_at_index():
    model = DictionaryListModel([(10, "Utilities"), (20, "Groceries")])
    assert model.data(model.index(0, 0), Qt.DisplayRole) == "Utilities"
    assert model.data(model.index(1, 0), Qt.DisplayRole) == "Groceries"


def test_dictionary_list_model_id_at_returns_id():
    model = DictionaryListModel([(10, "Utilities"), (20, "Groceries")])
    assert model.id_at(0) == 10
    assert model.id_at(1) == 20


def test_dictionary_list_model_row_count():
    model = DictionaryListModel([(10, "Utilities"), (20, "Groceries")])
    assert model.rowCount() == 2


def test_dictionary_list_model_set_items_replaces_contents():
    model = DictionaryListModel([(10, "Utilities")])
    model.set_items([(30, "Entertainment")])
    assert model.rowCount() == 1
    assert model.id_at(0) == 30
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_models.py -k dictionary_list -v`
Expected: FAIL with `ImportError: cannot import name 'DictionaryListModel'`

- [ ] **Step 3: Implement DictionaryListModel**

Add to `ui/models.py` (below the existing imports, `from PySide6.QtCore import QAbstractTableModel, Qt` becomes `from PySide6.QtCore import QAbstractListModel, QAbstractTableModel, Qt`):

```python
class DictionaryListModel(QAbstractListModel):
    def __init__(self, items=None, parent=None):
        super().__init__(parent)
        self._items = items or []

    def set_items(self, items):
        self.beginResetModel()
        self._items = items
        self.endResetModel()

    def id_at(self, row):
        return self._items[row][0]

    def rowCount(self, parent=None):
        return len(self._items)

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        return self._items[index.row()][1]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_models.py -k dictionary_list -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add ui/models.py ui/tests/test_models.py
git commit -m "Add DictionaryListModel for category/investment lists"
```

---

### Task 4: Model — CategoryTransactionTableModel

**Files:**
- Modify: `ui/models.py`
- Test: `ui/tests/test_models.py`

**Interfaces:**
- Consumes: row shape from `data.list_category_transactions` (Task 1): `(transaction_id, txn_date, account_name, payee, memo, amount)`.
- Produces: `models.CategoryTransactionTableModel(transactions=None, parent=None)` — a `QAbstractTableModel` with columns `["Date", "Account", "Payee", "Memo", "Amount"]`.
  - `.set_transactions(transactions)` — resets the model with a new list.
  - `.data(index, role)` — column order: Date (ISO string), Account, Payee (empty string if `None`), Memo (empty string if `None`), Amount (formatted `f"{amount:.2f}"`).

- [ ] **Step 1: Write the failing tests**

Add to `ui/tests/test_models.py`:

```python
from models import CategoryTransactionTableModel


def test_category_transaction_model_shows_date_and_account():
    model = CategoryTransactionTableModel(
        [(1000, date(2024, 3, 15), "Checking", "Store A", "weekly shop", Decimal("-52.30"))]
    )
    assert _data(model, 0, 0) == "2024-03-15"
    assert _data(model, 0, 1) == "Checking"


def test_category_transaction_model_formats_amount():
    model = CategoryTransactionTableModel(
        [(1000, date(2024, 3, 15), "Checking", "Store A", "weekly shop", Decimal("-52.30"))]
    )
    assert _data(model, 0, 4) == "-52.30"


def test_category_transaction_model_handles_missing_payee_and_memo():
    model = CategoryTransactionTableModel(
        [(1002, date(2024, 3, 1), "Checking", None, None, Decimal("-75.00"))]
    )
    assert _data(model, 0, 2) == ""
    assert _data(model, 0, 3) == ""


def test_category_transaction_model_row_and_column_count():
    model = CategoryTransactionTableModel(
        [(1000, date(2024, 3, 15), "Checking", "Store A", "weekly shop", Decimal("-52.30"))]
    )
    assert model.rowCount() == 1
    assert model.columnCount() == 5
```

(`_data` and the `date`/`Decimal` imports already exist at the top of `ui/tests/test_models.py` from the existing tests.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_models.py -k category_transaction -v`
Expected: FAIL with `ImportError: cannot import name 'CategoryTransactionTableModel'`

- [ ] **Step 3: Implement CategoryTransactionTableModel**

Add to `ui/models.py`:

```python
class CategoryTransactionTableModel(QAbstractTableModel):
    COLUMNS = ["Date", "Account", "Payee", "Memo", "Amount"]

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
        _, txn_date, account_name, payee, memo, amount = self._transactions[index.row()]
        values = [
            txn_date.isoformat(),
            account_name,
            payee or "",
            memo or "",
            f"{amount:.2f}",
        ]
        return values[index.column()]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd ui && ../.venv/bin/python -m pytest tests/test_models.py -k category_transaction -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Run the full test suite to confirm no regressions**

Run: `cd ui && ../.venv/bin/python -m pytest tests/ -v`
Expected: PASS, all tests including everything added in Tasks 1–4.

- [ ] **Step 6: Commit**

```bash
git add ui/models.py ui/tests/test_models.py
git commit -m "Add CategoryTransactionTableModel"
```

---

### Task 5: Widget — Categories pane

**Files:**
- Create: `ui/dictionaries_tab.py`

**Interfaces:**
- Consumes: `data.list_categories`, `data.list_category_transactions` (Task 1); `models.DictionaryListModel` (Task 3), `models.CategoryTransactionTableModel` (Task 4).
- Produces: `dictionaries_tab.CategoriesPane(conn, report_error, parent=None)` — a `QWidget`. `report_error` is a callable taking one `str` argument (wired to the main window's status bar in Task 7). Not unit-tested (widget code, per Global Constraints) — verified in Step 2 below by running the app standalone.

- [ ] **Step 1: Implement CategoriesPane**

Create `ui/dictionaries_tab.py`:

```python
"""Dictionaries tab: browse categories and investments across all accounts."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

import data
from models import CategoryTransactionTableModel, DictionaryListModel


class CategoriesPane(QWidget):
    def __init__(self, conn, report_error, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._report_error = report_error

        self.list_model = DictionaryListModel()
        self.detail_model = CategoryTransactionTableModel()

        self.list_view = QListView()
        self.list_view.setModel(self.list_model)
        self.list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_view.selectionModel().selectionChanged.connect(self._on_selected)

        self.detail_view = QTableView()
        self.detail_view.setModel(self.detail_model)
        self.detail_view.horizontalHeader().setStretchLastSection(True)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.list_view)
        splitter.addWidget(self.detail_view)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self._reload()

    def _reload(self):
        try:
            categories = data.list_categories(self._conn)
        except Exception as exc:
            self._report_error(f"Failed to load categories: {exc}")
            return
        self.list_model.set_items(categories)

    def _on_selected(self, selected=None, deselected=None):
        indexes = self.list_view.selectionModel().selectedIndexes()
        if not indexes:
            self.detail_model.set_transactions([])
            return
        category_id = self.list_model.id_at(indexes[0].row())
        try:
            transactions = data.list_category_transactions(self._conn, category_id)
        except Exception as exc:
            self._report_error(f"Failed to load category transactions: {exc}")
            return
        self.detail_model.set_transactions(transactions)
        self.detail_view.resizeColumnsToContents()
```

- [ ] **Step 2: Manually verify against the real database**

Run:

```bash
cd ui && ../.venv/bin/python -c "
import sys
sys.path.insert(0, '.')
import duckdb
from PySide6.QtWidgets import QApplication
from dictionaries_tab import CategoriesPane

app = QApplication(sys.argv)
conn = duckdb.connect('../money.duckdb', read_only=True)
pane = CategoriesPane(conn, print)
pane.resize(900, 500)
pane.show()
app.exec()
"
```

Expected: a window opens with a list of category names on the left. Clicking one populates the right-hand table with that category's transactions (Date/Account/Payee/Memo/Amount), sourced from more than one account for categories used broadly (e.g. a common expense category). Close the window to exit.

- [ ] **Step 3: Commit**

```bash
git add ui/dictionaries_tab.py
git commit -m "Add CategoriesPane widget for browsing category transactions"
```

---

### Task 6: Widget — Investments pane

**Files:**
- Modify: `ui/dictionaries_tab.py`

**Interfaces:**
- Consumes: `data.list_securities`, `data.list_security_history` (Task 2); `models.DictionaryListModel` (Task 3).
- Produces: `dictionaries_tab.InvestmentsPane(conn, report_error, parent=None)` — a `QWidget`, same `report_error` contract as `CategoriesPane`. Not unit-tested — verified in Step 2 below by running the app standalone.

- [ ] **Step 1: Implement InvestmentsPane**

Add to `ui/dictionaries_tab.py`. Update the imports at the top of the file:

```python
from PySide6.QtCharts import QChart, QChartView, QDateTimeAxis, QLineSeries, QValueAxis
from PySide6.QtCore import QDate, QDateTime, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)
```

Append the new class:

```python
class InvestmentsPane(QWidget):
    def __init__(self, conn, report_error, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._report_error = report_error

        self.list_model = DictionaryListModel()
        self.list_view = QListView()
        self.list_view.setModel(self.list_model)
        self.list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_view.selectionModel().selectionChanged.connect(self._on_selected)

        self.price_chart_view = QChartView()
        self.price_chart_view.setRenderHint(QPainter.Antialiasing)
        self.quantity_chart_view = QChartView()
        self.quantity_chart_view.setRenderHint(QPainter.Antialiasing)

        charts_widget = QWidget()
        charts_layout = QVBoxLayout(charts_widget)
        charts_layout.addWidget(self.price_chart_view)
        charts_layout.addWidget(self.quantity_chart_view)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.list_view)
        splitter.addWidget(charts_widget)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self._reload()

    def _reload(self):
        try:
            securities = data.list_securities(self._conn)
        except Exception as exc:
            self._report_error(f"Failed to load investments: {exc}")
            return
        self.list_model.set_items(securities)

    def _on_selected(self, selected=None, deselected=None):
        indexes = self.list_view.selectionModel().selectedIndexes()
        if not indexes:
            self.price_chart_view.setChart(QChart())
            self.quantity_chart_view.setChart(QChart())
            return
        security_id = self.list_model.id_at(indexes[0].row())
        try:
            history = data.list_security_history(self._conn, security_id)
        except Exception as exc:
            self._report_error(f"Failed to load investment history: {exc}")
            return

        price_by_account = {}
        qty_by_account = {}
        for _account_id, account_name, txn_date, price, cumulative_qty in history:
            if price is not None:
                price_by_account.setdefault(account_name, []).append((txn_date, price))
            qty_by_account.setdefault(account_name, []).append((txn_date, cumulative_qty))

        self.price_chart_view.setChart(self._build_line_chart("Price", price_by_account))
        self.quantity_chart_view.setChart(
            self._build_line_chart("Quantity Held", qty_by_account)
        )

    @staticmethod
    def _build_line_chart(title, series_by_account):
        chart = QChart()
        chart.setTitle(title)
        axis_x = QDateTimeAxis()
        axis_x.setFormat("yyyy-MM-dd")
        axis_y = QValueAxis()
        chart.addAxis(axis_x, Qt.AlignBottom)
        chart.addAxis(axis_y, Qt.AlignLeft)
        for account_name, points in series_by_account.items():
            series = QLineSeries()
            series.setName(account_name)
            for txn_date, value in points:
                qdt = QDateTime(QDate(txn_date.year, txn_date.month, txn_date.day))
                series.append(qdt.toMSecsSinceEpoch(), float(value))
            chart.addSeries(series)
            series.attachAxis(axis_x)
            series.attachAxis(axis_y)
        return chart
```

- [ ] **Step 2: Manually verify against the real database**

Run:

```bash
cd ui && ../.venv/bin/python -c "
import sys
sys.path.insert(0, '.')
import duckdb
from PySide6.QtWidgets import QApplication
from dictionaries_tab import InvestmentsPane

app = QApplication(sys.argv)
conn = duckdb.connect('../money.duckdb', read_only=True)
pane = InvestmentsPane(conn, print)
pane.resize(900, 700)
pane.show()
app.exec()
"
```

Expected: a window opens with a list of security names on the left. Clicking one shows two stacked charts on the right — price over time on top, cumulative quantity held over time below — with one line per account holding that security (only one line if held in a single account). A security with no Buy/Sell activity shows empty charts, not an error. Close the window to exit.

- [ ] **Step 3: Commit**

```bash
git add ui/dictionaries_tab.py
git commit -m "Add InvestmentsPane widget with price/quantity charts"
```

---

### Task 7: Wire the Dictionaries tab into the main window

**Files:**
- Modify: `ui/main_window.py`

**Interfaces:**
- Consumes: `dictionaries_tab.CategoriesPane`, `dictionaries_tab.InvestmentsPane` (Tasks 5–6).
- Produces: `MainWindow`'s central widget is now a `QTabWidget` with two top-level tabs, "Accounts" (existing splitter, unchanged content) and "Dictionaries" (new `QTabWidget` with "Categories"/"Investments" sub-tabs).

- [ ] **Step 1: Wrap the central widget in a top-level QTabWidget**

In `ui/main_window.py`, add `QTabWidget` to the `PySide6.QtWidgets` import list, and add a new import:

```python
from dictionaries_tab import CategoriesPane, InvestmentsPane
```

Replace the tail of `MainWindow.__init__` (from the existing `splitter = QSplitter(...)` block through `self.setCentralWidget(splitter)`) with:

```python
        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        dictionaries_tabs = QTabWidget()
        dictionaries_tabs.addTab(
            CategoriesPane(self._conn, self.statusBar().showMessage), "Categories"
        )
        dictionaries_tabs.addTab(
            InvestmentsPane(self._conn, self.statusBar().showMessage), "Investments"
        )

        tabs = QTabWidget()
        tabs.addTab(splitter, "Accounts")
        tabs.addTab(dictionaries_tabs, "Dictionaries")
        self.setCentralWidget(tabs)
```

- [ ] **Step 2: Run the full automated test suite**

Run: `cd ui && ../.venv/bin/python -m pytest tests/ -v`
Expected: PASS, all tests (Tasks 1–4's new tests plus every pre-existing test) — this task's own change is widget wiring and isn't itself unit-tested.

- [ ] **Step 3: Manually run the full app**

Run: `./run-ui.sh` from the project root.

Expected:
- Window opens showing "Accounts" and "Dictionaries" tabs.
- "Accounts" tab behaves exactly as before (account list, transaction drill-down, exchange rate, closed-accounts toggle).
- "Dictionaries" tab shows "Categories" and "Investments" sub-tabs, each behaving as verified standalone in Tasks 5 and 6.
- No exceptions in the terminal on startup or when clicking through both tabs and several list items in each.

- [ ] **Step 4: Commit**

```bash
git add ui/main_window.py
git commit -m "Add Dictionaries tab to main window"
```
