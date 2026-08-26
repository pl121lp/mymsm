"""Qt table models adapting data.py query results for QTableViews."""

import calendar
from decimal import Decimal

from PySide6.QtCore import QAbstractListModel, QAbstractTableModel, Qt
from PySide6.QtGui import QFont

from data import ASSET_ACCOUNT_TYPE, BUY_ACTIVITY, INVESTMENT_ACCOUNT_TYPE, LOAN_ACCOUNT_TYPE, SELL_ACTIVITY

ACCOUNT_TYPE_LABELS = {
    "0": "Checking/Savings",
    "1": "Credit",
    "5": "Investment",
    "3": "Asset",
    "6": "Loan",
}


def account_type_label(account_type):
    if account_type is None:
        return ""
    return ACCOUNT_TYPE_LABELS.get(account_type, f"Type {account_type}")


ACTIVITY_LABELS = {
    "1": "Buy",
    "2": "Sell",
}


def activity_label(activity):
    if activity is None:
        return ""
    return ACTIVITY_LABELS.get(activity, f"Activity {activity}")


def format_currency(amount):
    return f"{amount:,.2f}"


def format_quantity(quantity):
    if quantity is None:
        return ""
    return f"{quantity:,.4f}"


PRIMARY_CURRENCY = "USD"


def compute_account_value_history(transactions, opening_balance, is_investment):
    """Running account value over time, from data.list_transactions() rows.

    For non-investment accounts this is the opening balance plus a running
    cumulative sum of transaction amounts. For investment accounts it's the
    running (quantity * latest known price) summed across held securities,
    using the same buy/sell signed-quantity logic as data.list_accounts().
    """
    ordered = sorted(transactions, key=lambda row: row[1])

    if not is_investment:
        balance = opening_balance if opening_balance is not None else Decimal("0")
        history = []
        for row in ordered:
            balance += row[5]
            history.append((row[1], balance))
        return history

    quantities = {}
    prices = {}
    history = []
    for row in ordered:
        txn_date, security, activity, quantity, price = row[1], row[6], row[7], row[8], row[9]
        if security is None or activity not in (BUY_ACTIVITY, SELL_ACTIVITY):
            continue
        signed_qty = -quantity if activity == SELL_ACTIVITY else quantity
        quantities[security] = quantities.get(security, Decimal("0")) + signed_qty
        if price is not None:
            prices[security] = price
        total = sum(
            (quantities[sec] * prices[sec] for sec in quantities if sec in prices),
            start=Decimal("0"),
        )
        history.append((txn_date, total))
    return history


def build_loan_transaction_rows(transactions, interest_payments):
    """Merges a loan account's real (Principal) transactions with its
    reconstructed (Interest) payments into TransactionTableModel's loan row
    shape, sorted by date descending (Principal before Interest on ties).

    `transactions` matches data.list_transactions()'s row shape;
    `interest_payments` matches data.list_loan_interest_payments()'s
    (txn_date, payee, amount) shape. Interest rows carry no transaction_id
    since they aren't editable/deletable records of their own — they're
    reconstructed from a different account's transactions.
    """
    rows = [
        (transaction_id, txn_date, payee, category, memo, amount, None, None, None, None, "Principal")
        for transaction_id, txn_date, payee, category, memo, amount, *_rest in transactions
    ]
    rows += [
        (None, txn_date, payee, None, None, amount, None, None, None, None, "Interest")
        for txn_date, payee, amount, _currency in interest_payments
    ]
    rows.sort(key=lambda row: row[1], reverse=True)
    return rows


def compute_loan_totals(transactions, interest_payments, to_usd):
    """(total_principal, total_interest_usd) paid on a loan account.

    total_principal is the sum of the loan account's own transaction
    amounts (data.list_transactions() row shape, native currency) — since
    balance = opening balance + running sum of those amounts, this equals
    the lifetime amount financed. total_interest_usd sums the reconstructed
    interest payments (data.list_loan_interest_payments() row shape),
    converting each individually via to_usd(currency, amount): interest legs
    come from the paying account, which may be denominated differently than
    the loan itself.
    """
    total_principal = sum((row[5] for row in transactions), start=Decimal("0"))
    total_interest = sum(
        (to_usd(currency, amount) for _txn_date, _payee, amount, currency in interest_payments),
        start=Decimal("0"),
    )
    return total_principal, total_interest


def _add_months(base_date, months):
    month_index = base_date.month - 1 + months
    year = base_date.year + month_index // 12
    month = month_index % 12 + 1
    day = min(base_date.day, calendar.monthrange(year, month)[1])
    return base_date.replace(year=year, month=month, day=day)


def generate_sample_dates(earliest, latest, months=3):
    """Dates from earliest to latest spaced `months` apart, always ending at latest."""
    dates = []
    current = earliest
    while current < latest:
        dates.append(current)
        current = _add_months(current, months)
    dates.append(latest)
    return dates


def compute_net_worth_series(accounts, sample_dates, to_usd):
    """Total account value (USD) at each sample date.

    accounts is an iterable of (currency, initial_value, history) tuples,
    where history is a compute_account_value_history()-style ascending list
    of (date, value) and initial_value is the value before its first entry
    (opening balance for cash accounts, zero for investment accounts).
    """
    series = []
    for sample_date in sample_dates:
        total = Decimal("0")
        for currency, initial_value, history in accounts:
            value = initial_value
            for txn_date, txn_value in history:
                if txn_date > sample_date:
                    break
                value = txn_value
            total += to_usd(currency, value)
        series.append((sample_date, total))
    return series


def compute_spending_by_category(transactions, start, end, to_usd):
    """Total spending (USD) per category within [start, end], highest first.

    `transactions` are (category_id, category_name, txn_date, amount, currency)
    rows, e.g. from data.list_category_spending(). Only negative amounts (money
    out) count as spending; positive amounts (refunds, income posted to a
    spending category) are ignored.
    """
    totals = {}
    for _category_id, category_name, txn_date, amount, currency in transactions:
        if txn_date < start or txn_date > end or amount >= 0:
            continue
        totals[category_name] = totals.get(category_name, Decimal("0")) + to_usd(currency, -amount)
    return sorted(totals.items(), key=lambda item: item[1], reverse=True)


def compute_income_by_category(transactions, start, end, to_usd):
    """Total income (USD) per category within [start, end], highest first.

    `transactions` are (category_id, category_name, txn_date, amount, currency)
    rows, e.g. from data.list_category_spending(). Only positive amounts (money
    in) count as income; negative amounts (spending posted to an income
    category) are ignored.
    """
    totals = {}
    for _category_id, category_name, txn_date, amount, currency in transactions:
        if txn_date < start or txn_date > end or amount <= 0:
            continue
        totals[category_name] = totals.get(category_name, Decimal("0")) + to_usd(currency, amount)
    return sorted(totals.items(), key=lambda item: item[1], reverse=True)


class SpendingByCategoryTableModel(QAbstractTableModel):
    COLUMNS = ["Category", "Spending (USD)"]

    def __init__(self, categories=None, parent=None):
        super().__init__(parent)
        self._categories = categories or []

    def set_categories(self, categories):
        self.beginResetModel()
        self._categories = categories
        self.endResetModel()

    def category_at(self, row):
        return self._categories[row]

    def rowCount(self, parent=None):
        return len(self._categories)

    def columnCount(self, parent=None):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        category_name, total = self._categories[index.row()]
        values = [category_name, format_currency(total)]
        return values[index.column()]


class IncomeByCategoryTableModel(SpendingByCategoryTableModel):
    COLUMNS = ["Category", "Income (USD)"]


def compute_investment_analysis(prices, start, end):
    """Per-investment price gain within [start, end], highest % increase first.

    `prices` are (security_name, txn_date, price) rows, e.g. from
    data.list_investment_prices(). % increase is (highest - lowest) / lowest
    over whatever priced trades fall in range, regardless of their order in
    time. Investments with no priced trades in range are omitted.
    """
    points_by_name = {}
    for name, txn_date, price in prices:
        if txn_date < start or txn_date > end:
            continue
        points_by_name.setdefault(name, []).append((txn_date, price))

    results = []
    for name, points in points_by_name.items():
        dates = [txn_date for txn_date, _price in points]
        security_prices = [price for _txn_date, price in points]
        lowest = min(security_prices)
        highest = max(security_prices)
        pct_increase = (highest - lowest) / lowest * 100 if lowest else Decimal("0")
        results.append((name, pct_increase, lowest, highest, min(dates), max(dates)))

    return sorted(results, key=lambda item: item[1], reverse=True)


class InvestmentAnalysisTableModel(QAbstractTableModel):
    COLUMNS = ["Investment", "% Increase", "Lowest Price", "Highest Price", "Date Range"]

    def __init__(self, investments=None, parent=None):
        super().__init__(parent)
        self._investments = investments or []

    def set_investments(self, investments):
        self.beginResetModel()
        self._investments = investments
        self.endResetModel()

    def investment_at(self, row):
        return self._investments[row]

    def sort(self, column, order=Qt.AscendingOrder):
        if not self._investments:
            return
        self.layoutAboutToBeChanged.emit()
        self._investments.sort(key=lambda item: item[column], reverse=order == Qt.DescendingOrder)
        self.layoutChanged.emit()

    def rowCount(self, parent=None):
        return len(self._investments)

    def columnCount(self, parent=None):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        name, pct_increase, lowest, highest, first_date, last_date = self._investments[index.row()]
        values = [
            name,
            f"{pct_increase:+.2f}%",
            format_currency(lowest),
            format_currency(highest),
            f"{first_date.isoformat()} to {last_date.isoformat()}",
        ]
        return values[index.column()]


def compute_assets_and_investments(accounts, to_usd):
    """Report rows (USD) grouping open accounts into investments, assets,
    and loans/liabilities, each followed by its subtotal, ending with the
    overall total balance (assets + investments - loans).

    accounts is data.list_accounts()-style rows: (account_id, name,
    account_type, currency, balance, is_closed). Loan balances are stored
    negative (debt owed); shown here as a positive value that is subtracted
    from the total.

    Returns a list of (type_label, name, value, emphasized) rows suitable
    for AssetsAndInvestmentsTableModel.set_rows(). Section header rows
    carry the section label in type_label and leave name/value blank;
    account and total rows leave type_label blank and are indented under
    their section by appearing in the name/value columns instead. value
    is None for section header rows.
    """
    investments = []
    assets = []
    loans = []
    for _account_id, name, account_type, currency, balance, _is_closed in accounts:
        usd_value = to_usd(currency, balance)
        if account_type == INVESTMENT_ACCOUNT_TYPE:
            investments.append((name, usd_value))
        elif account_type == ASSET_ACCOUNT_TYPE:
            assets.append((name, usd_value))
        elif account_type == LOAN_ACCOUNT_TYPE:
            loans.append((name, -usd_value))

    investments.sort(key=lambda row: row[0])
    assets.sort(key=lambda row: row[0])
    loans.sort(key=lambda row: row[0])

    investment_total = sum((value for _name, value in investments), start=Decimal("0"))
    asset_total = sum((value for _name, value in assets), start=Decimal("0"))
    loan_total = sum((value for _name, value in loans), start=Decimal("0"))
    total_balance = investment_total + asset_total - loan_total

    rows = [("Investments", "", None, True)]
    rows += [("", name, value, False) for name, value in investments]
    rows.append(("", "Total Investments", investment_total, True))
    rows.append(("Assets", "", None, True))
    rows += [("", name, value, False) for name, value in assets]
    rows.append(("", "Total Assets", asset_total, True))
    rows.append(("Loans / Liabilities", "", None, True))
    rows += [("", name, value, False) for name, value in loans]
    rows.append(("", "Total Loans", loan_total, True))
    rows.append(("", "Total Balance", total_balance, True))
    return rows


class AssetsAndInvestmentsTableModel(QAbstractTableModel):
    COLUMNS = ["Account Type", "Account", "Value (USD)"]

    def __init__(self, rows=None, parent=None):
        super().__init__(parent)
        self._rows = rows or []

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def rowCount(self, parent=None):
        return len(self._rows)

    def columnCount(self, parent=None):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        type_label, name, value, emphasized = self._rows[index.row()]
        if role == Qt.DisplayRole:
            if index.column() == 0:
                return type_label
            if index.column() == 1:
                return name
            return format_currency(value) if value is not None else ""
        if role == Qt.FontRole and emphasized:
            font = QFont()
            font.setBold(True)
            return font
        return None


class AccountTableModel(QAbstractTableModel):
    COLUMNS = ["Name", "Type", "Currency", "Balance"]

    def __init__(self, accounts=None, parent=None):
        super().__init__(parent)
        self._accounts = accounts or []
        self._exchange_rates = {}

    def set_accounts(self, accounts):
        self.beginResetModel()
        self._accounts = accounts
        self.endResetModel()

    def set_exchange_rates(self, exchange_rates):
        self._exchange_rates = exchange_rates
        if self._accounts:
            balance_col = self.COLUMNS.index("Balance")
            top_left = self.index(0, balance_col)
            bottom_right = self.index(self.rowCount() - 1, balance_col)
            self.dataChanged.emit(top_left, bottom_right)

    def to_usd(self, currency, amount):
        if currency == PRIMARY_CURRENCY:
            return amount
        rate = self._exchange_rates.get(currency)
        if rate is None:
            return amount
        return amount * rate

    def total_usd(self):
        return sum(
            (
                self.to_usd(currency, balance)
                for _, _, _, currency, balance, is_closed in self._accounts
                if not is_closed
            ),
            start=Decimal("0"),
        )

    def sort(self, column, order=Qt.AscendingOrder):
        if not self._accounts:
            return
        reverse = order == Qt.DescendingOrder
        if column == self.COLUMNS.index("Name"):
            key = lambda row: row[1].lower()
        elif column == self.COLUMNS.index("Type"):
            key = lambda row: account_type_label(row[2]).lower()
        elif column == self.COLUMNS.index("Currency"):
            key = lambda row: row[3]
        elif column == self.COLUMNS.index("Balance"):
            key = lambda row: self.to_usd(row[3], row[4])
        else:
            return
        self.layoutAboutToBeChanged.emit()
        self._accounts.sort(key=key, reverse=reverse)
        self.layoutChanged.emit()

    def account_id_at(self, row):
        return self._accounts[row][0]

    def account_at(self, row):
        return self._accounts[row]

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
        _, name, account_type, currency, balance, is_closed = self._accounts[index.row()]
        values = [
            f"(CLOSED) {name}" if is_closed else name,
            account_type_label(account_type),
            currency,
            format_currency(self.to_usd(currency, balance)),
            "",
        ]
        return values[index.column()]


class TransactionTableModel(QAbstractTableModel):
    DEFAULT_COLUMNS = ["Date", "Payee", "Category", "Memo", "Amount"]
    INVESTMENT_COLUMNS = ["Date", "Investment", "Activity", "Quantity", "Price", "Amount", "Memo"]
    LOAN_COLUMNS = ["Date", "Payee", "Type", "Memo", "Amount"]

    # Maps each column set's display columns to the underlying transaction
    # tuple index (see data.py's list_transactions row shape). Loan rows come
    # from build_loan_transaction_rows(), which appends "kind" (Principal/
    # Interest) as an 11th field.
    DEFAULT_FIELD_INDEXES = [1, 2, 3, 4, 5]
    INVESTMENT_FIELD_INDEXES = [1, 6, 7, 8, 9, 5, 4]
    LOAN_FIELD_INDEXES = [1, 2, 10, 4, 5]

    def __init__(self, transactions=None, parent=None, is_investment=False, is_loan=False):
        super().__init__(parent)
        self._transactions = transactions or []
        self._is_investment = is_investment
        self._is_loan = is_loan

    def set_transactions(self, transactions, is_investment=False, is_loan=False):
        self.beginResetModel()
        self._transactions = transactions
        self._is_investment = is_investment
        self._is_loan = is_loan
        self.endResetModel()

    def transaction_at(self, row):
        return self._transactions[row]

    @property
    def _columns(self):
        if self._is_investment:
            return self.INVESTMENT_COLUMNS
        if self._is_loan:
            return self.LOAN_COLUMNS
        return self.DEFAULT_COLUMNS

    @property
    def _field_indexes(self):
        if self._is_investment:
            return self.INVESTMENT_FIELD_INDEXES
        if self._is_loan:
            return self.LOAN_FIELD_INDEXES
        return self.DEFAULT_FIELD_INDEXES

    def sort(self, column, order=Qt.AscendingOrder):
        if not self._transactions:
            return
        field_index = self._field_indexes[column]
        self.layoutAboutToBeChanged.emit()
        known = [row for row in self._transactions if row[field_index] is not None]
        unknown = [row for row in self._transactions if row[field_index] is None]
        known.sort(key=lambda row: row[field_index], reverse=(order == Qt.DescendingOrder))
        self._transactions = known + unknown
        self.layoutChanged.emit()

    def rowCount(self, parent=None):
        return len(self._transactions)

    def columnCount(self, parent=None):
        return len(self._columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self._columns[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        row = self._transactions[index.row()]
        _, txn_date, payee, category, memo, amount, investment, activity, quantity, price = row[:10]
        if self._is_investment:
            values = [
                txn_date.isoformat(),
                investment or "",
                activity_label(activity),
                format_quantity(quantity),
                format_quantity(price),
                f"{amount:.2f}",
                memo or "",
            ]
        elif self._is_loan:
            kind = row[10]
            values = [
                txn_date.isoformat(),
                payee or "",
                kind,
                memo or "",
                f"{amount:.2f}",
            ]
        else:
            values = [
                txn_date.isoformat(),
                payee or "",
                category or "",
                memo or "",
                f"{amount:.2f}",
            ]
        return values[index.column()]


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


class SearchResultTableModel(QAbstractTableModel):
    COLUMNS = ["Date", "Account", "Payee", "Category", "Investment", "Memo", "Amount"]

    def __init__(self, results=None, parent=None):
        super().__init__(parent)
        self._results = results or []

    def set_results(self, results):
        self.beginResetModel()
        self._results = results
        self.endResetModel()

    def account_info_at(self, row):
        _, _, account_id, _, account_type, *_ = self._results[row]
        return account_id, account_type

    def transaction_at(self, row):
        (
            transaction_id, txn_date, _account_id, _account_name, _account_type,
            payee, category, memo, amount, security, activity, quantity, price,
        ) = self._results[row]
        return (
            transaction_id, txn_date, payee, category, memo, amount,
            security, activity, quantity, price,
        )

    def rowCount(self, parent=None):
        return len(self._results)

    def columnCount(self, parent=None):
        return len(self.COLUMNS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.COLUMNS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        (
            _transaction_id, txn_date, _account_id, account_name, _account_type,
            payee, category, memo, amount, security, _activity, _quantity, _price,
        ) = self._results[index.row()]
        values = [
            txn_date.isoformat(),
            account_name,
            payee or "",
            category or "",
            security or "",
            memo or "",
            f"{amount:.2f}",
        ]
        return values[index.column()]


class PayeeTransactionTableModel(QAbstractTableModel):
    COLUMNS = ["Date", "Account", "Category", "Memo", "Amount"]

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
        _, txn_date, account_name, category, memo, amount = self._transactions[index.row()]
        values = [
            txn_date.isoformat(),
            account_name,
            category or "",
            memo or "",
            f"{amount:.2f}",
        ]
        return values[index.column()]
