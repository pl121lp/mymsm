# Dictionaries Browsing UI (Categories & Investments) — Design

Date: 2026-08-19
Status: Approved for implementation

## Problem

The desktop browser (see `2026-08-18-desktop-ui-design.md`) shows accounts
and, per account, that account's transactions. Categories (231 rows) and
securities/investments (182 rows) already exist as dictionary tables in
`money.duckdb` and are joined into the transaction view, but there's no way
to browse them on their own terms: see every transaction tagged with a
category regardless of account, or see a security's price and holdings
history over time.

## Constraints & context

- Same dataset/performance characteristics as the existing UI — all queries
  are single-digit milliseconds, no caching or async needed.
- The app is currently **read-only**; there is no add/edit-record UI yet.
  The original request described dictionaries being used "when adding new
  records" and auto-growing when a new investment name is typed — that
  presumes an add-record feature. Confirmed during brainstorming: **that
  feature does not exist and is not built here.** This iteration only adds
  the dictionaries' browsing UI, reading `categories`/`securities` as they
  already exist. Auto-populating the investment dictionary from new entries
  is deferred until an add-record feature is actually designed, since
  there'd be nothing to test that behavior against right now.
- Confirmed during brainstorming:
  - New "Dictionaries" tab, reached via top-level tabs (Accounts /
    Dictionaries) added to the main window.
  - Investment detail is a per-account breakdown (separate series per
    account holding a security), not aggregated across accounts.
  - Quantity-over-time is a cumulative running total (holdings over time),
    using the same buy/sell-only logic already used for account valuation.
  - Price and quantity are two separate stacked charts, not one dual-axis
    chart.
  - Category detail's transaction list includes an Account column, since
    it spans all accounts unlike the existing per-account transaction view.
  - Charting uses `PySide6.QtCharts`, already bundled with the installed
    `PySide6` dependency — no new package.

## Architecture

Extends the existing `ui/` package; no new top-level modules for data
access, following the existing `data.py`/`models.py`/widget split.

```
ui/
  data.py          + list_categories(conn)
                    + list_category_transactions(conn, category_id)
                    + list_securities(conn)
                    + list_security_history(conn, security_id)
  models.py         + DictionaryListModel (QAbstractListModel; reused for
                      both categories and investments)
                    + CategoryTransactionTableModel (QAbstractTableModel;
                      Date/Account/Payee/Memo/Amount)
  main_window.py    MainWindow's central widget becomes a QTabWidget:
                      - "Accounts": existing splitter, unchanged
                      - "Dictionaries": new DictionariesTab widget
  dictionaries_tab.py   (new) QTabWidget with "Categories" and
                    "Investments" sub-tabs, each a left-list/right-detail
                    QSplitter mirroring the Accounts tab's pattern
```

`dictionaries_tab.py` is a new file, not folded into `main_window.py`,
because it owns two independent list+detail panes (category and
investment) with enough wiring (list selection → query → chart/table
population) that inlining it would make `main_window.py` do two unrelated
jobs. `main_window.py` only instantiates it and adds it as a tab.

Rejected alternatives:
- **Single list with a toggle, QStackedWidget detail** — one list switching
  between categories/investments via radio buttons, with the detail pane
  swapping between a table and charts. Rejected: more state to manage
  (what's currently selected in each mode) for no real benefit over two
  plain sub-tabs, which also matches the existing Accounts tab's pattern
  more directly.
- **matplotlib for charts** — more familiar plotting API, but adds a new
  dependency and an embedding shim (`FigureCanvasQTAgg`) when
  `PySide6.QtCharts` is already installed and gives native Qt widgets.

## Data flow

1. **Categories sub-tab**: on tab creation, `dictionaries_tab.py` calls
   `data.list_categories(conn)` and populates the left `QListView` via
   `DictionaryListModel`, sorted by name. Selecting a category calls
   `data.list_category_transactions(conn, category_id)`, which joins
   `transactions` to `accounts` (for the account name), `payees`, and
   filters by `category_id`, sorted by `txn_date` descending. Populates the
   right `QTableView` via `CategoryTransactionTableModel`.

2. **Investments sub-tab**: on tab creation, calls `data.list_securities(conn)`
   and populates the left `QListView`. Selecting a security calls
   `data.list_security_history(conn, security_id)`, which:
   - Filters `transactions` to that `security_id` with `activity IN ('1',
     '2')` (Buy/Sell — same constants as `data.py`'s existing
     `BUY_ACTIVITY`/`SELL_ACTIVITY`), like `list_accounts` already does.
   - For each `account_id` holding the security, orders its transactions by
     `txn_date` and computes a running cumulative signed quantity (Sell
     negates, matching existing logic).
   - Returns rows shaped `(account_id, account_name, txn_date, price,
     cumulative_qty)`, ordered by account then date.

   `dictionaries_tab.py` groups these rows by `account_id` and draws:
   - Top `QChartView`: one `QLineSeries` per account, x = date, y = price
     (only points where `price IS NOT NULL`).
   - Bottom `QChartView`: one `QLineSeries` per account, x = date, y =
     cumulative_qty.
   Both charts use `QDateTimeAxis` for x and `QValueAxis` for y, legend
   labeled by account name.

3. No write operations anywhere in this feature. Every interaction is a
   fresh, cheap query, same as the existing Accounts tab.

## Error handling

Same convention as the existing Accounts tab: a failed query in
`dictionaries_tab.py` is caught at the call site and reported via the main
window's status bar (accessed through the parent), not a crash. A security
with no Buy/Sell activity (e.g. only transfers/grants, per the existing
README caveat) yields empty chart series rather than an error — same
"undercounted" caveat already documented for account valuation applies
here.

## Testing & packaging

- `data.py`'s four new functions get `pytest` coverage against the existing
  fixture DuckDB in `ui/tests/conftest.py` (extending its seed data as
  needed for multi-account security history), following `test_data.py`'s
  pattern: exact expected-row assertions.
- `DictionaryListModel` and `CategoryTransactionTableModel` get
  direct-construction tests in `test_models.py`, following its existing
  pattern (construct model with literal tuples, assert `data()` at
  specific indexes).
- `dictionaries_tab.py` (chart/list wiring) is not covered by automated
  tests, consistent with the existing convention for widget code
  (`main_window.py`) — verified by running the app.
- No new dependencies; `PySide6.QtCharts` is already available in the
  installed `PySide6` package.

## Out of scope (this iteration)

- Any add/edit-record UI, and the "auto-add new investment name to
  dictionary" behavior that depends on it.
- Editing category or security names, or merging/deleting dictionary
  entries.
- Filtering/searching within the category transaction list or the
  investment list.
