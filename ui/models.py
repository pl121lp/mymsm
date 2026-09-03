"""Qt table models adapting data.py query results for QTableViews."""

import statistics
from collections import Counter
from datetime import date
from decimal import Decimal

from PySide6.QtCore import QAbstractListModel, QAbstractTableModel, Qt
from PySide6.QtGui import QColor, QFont

import theme
from dateutils import add_months
from payee_merge import find_merge_groups, normalize
from data import (
    ASSET_ACCOUNT_TYPE,
    BUY_ACTIVITY,
    INVESTMENT_ACCOUNT_TYPE,
    LOAN_ACCOUNT_TYPE,
    RSU_SELL_ACTIVITY,
    SELL_ACTIVITY,
    VEST_ACTIVITY,
)

FAVORITE_BACKGROUND_LIGHT = QColor(225, 225, 225)
FAVORITE_BACKGROUND_DARK = QColor(70, 70, 70)

IMPORTED_BACKGROUND_LIGHT = QColor(200, 255, 200)
IMPORTED_BACKGROUND_DARK = QColor(40, 90, 40)

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
    "17": "Grant",
    "18": "Vested",
    "19": "Sold",
    "20": "Expired",
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


def compute_account_value_history(transactions, opening_balance, is_investment, today=None):
    """Running account value over time, from data.list_transactions() rows.

    For non-investment accounts this is the opening balance plus a running
    cumulative sum of transaction amounts. For investment accounts it's the
    running (quantity * latest known price) summed across held securities,
    using the same buy/sell/vest/RSU-sell signed-quantity logic as
    data.list_accounts(). RSU grant (17) and expiration (20) activity never
    affect quantity. Transactions dated after `today` (default: today's real
    date) are skipped entirely -- Money pre-records a grant's whole future
    vesting schedule up front, and those shares aren't held yet.
    """
    ordered = sorted(transactions, key=lambda row: row[1])

    if not is_investment:
        balance = opening_balance if opening_balance is not None else Decimal("0")
        history = []
        for row in ordered:
            balance += row[5]
            history.append((row[1], balance))
        return history

    today = today or date.today()
    quantities = {}
    prices = {}
    history = []
    for row in ordered:
        txn_date, security, activity, quantity, price = row[1], row[6], row[7], row[8], row[9]
        if security is None or activity not in (BUY_ACTIVITY, SELL_ACTIVITY, VEST_ACTIVITY, RSU_SELL_ACTIVITY):
            continue
        if txn_date > today:
            continue
        signed_qty = -quantity if activity in (SELL_ACTIVITY, RSU_SELL_ACTIVITY) else quantity
        quantities[security] = quantities.get(security, Decimal("0")) + signed_qty
        if price is not None and price > 0:
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


def generate_sample_dates(earliest, latest, months=3):
    """Dates from earliest to latest spaced `months` apart, always ending at latest."""
    dates = []
    current = earliest
    while current < latest:
        dates.append(current)
        current = add_months(current, months)
    dates.append(latest)
    return dates


def compute_net_worth_series(accounts, sample_dates, to_usd):
    """Total account value (USD) at each sample date.

    accounts is an iterable of (currency, initial_value, history, date_opened,
    is_closed) tuples, where history is a compute_account_value_history()-style
    ascending list of (date, value), initial_value is the value before its
    first entry (opening balance for cash accounts, zero for investment
    accounts), date_opened is the account's opening date (None if unknown),
    and is_closed marks accounts that no longer exist today.

    When date_opened is known, an account contributes nothing before it was
    opened -- the earlier of date_opened and its first transaction, since
    Money's recorded open date isn't always accurate -- so a nonzero
    initial_value (e.g. a loan's original principal) doesn't get counted
    for periods before the account existed. date_opened of None means
    unknown, not "always existed": no lower bound is applied, matching the
    old unconditional behavior. A closed account also contributes nothing
    after its last recorded transaction, rather than carrying forward
    whatever balance its history happened to end on (closed accounts often
    don't reconcile to exactly zero, e.g. a loan paid off via refinance
    with no offsetting transaction).
    """
    series = []
    for sample_date in sample_dates:
        total = Decimal("0")
        for currency, initial_value, history, date_opened, is_closed in accounts:
            first_active = date_opened
            if date_opened is not None and history and history[0][0] < date_opened:
                first_active = history[0][0]
            if first_active is not None and sample_date < first_active:
                continue
            if is_closed and history and sample_date > history[-1][0]:
                continue
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


# (label, target gap in days, tolerance in days, occurrences per year) for
# classifying the gaps between a payee's charges into a billing interval.
# Ranges don't overlap (weekly/biweekly/monthly/quarterly/annual are each
# well separated), so at most one bucket can match a given median gap.
_RECURRING_INTERVAL_BUCKETS = [
    ("Weekly", 7, 2, 52),
    ("Biweekly", 14, 3, 26),
    ("Monthly", 30, 5, 12),
    ("Quarterly", 91, 10, 4),
    ("Annual", 365, 15, 1),
]

# A gap is still "consistent" with a bucket if it's close to a small integer
# multiple of the target -- a bill paid a month late, or one payment that
# got skipped and caught up next cycle, still reads as the same underlying
# cadence, not a different one.
_MAX_SKIPPED_PERIODS = 3
# At least this fraction of gaps must be consistent, not all of them -- a
# lone one-off correction/reversal entry a day apart, or a single truly
# missed payment, shouldn't disqualify an otherwise clearly regular series.
_INTERVAL_MAJORITY_THRESHOLD = 0.8


def _classify_recurring_interval(gaps):
    """Match a sorted list of day-gaps to a billing interval, or None if irregular."""
    median_gap = statistics.median(gaps)
    for label, target, tolerance, periods_per_year in _RECURRING_INTERVAL_BUCKETS:
        if abs(median_gap - target) > tolerance:
            continue
        consistent = sum(
            1
            for gap in gaps
            if any(abs(gap - k * target) <= tolerance for k in range(1, _MAX_SKIPPED_PERIODS + 1))
        )
        if consistent / len(gaps) >= _INTERVAL_MAJORITY_THRESHOLD:
            return label, periods_per_year
    return None, None


# A single payee often represents more than one concurrently-billed amount --
# a mortgage statement split into principal/escrow/fee/total lines, two
# different insurance policies paid to the same insurer -- so a payee's
# transactions are first split into these amount sub-series before checking
# each for recurrence, rather than being averaged into one meaningless
# median that would reject all of them. Consecutive *sorted* amounts within
# this ratio of each other stay in the same sub-series: loose enough to ride
# out a single price increase (an HOA raising dues 15%) or a mortgage's
# gradual escrow drift, tight enough to split apart genuinely different
# bills (a $67 policy vs. a $110 one).
_AMOUNT_CLUSTER_MAX_STEP_RATIO = Decimal("1.20")
# Sub-series priced below this are almost always a rounding/balancing split
# line (e.g. a statement's "$0.01" adjustment), not a real recurring cost.
_MIN_RECURRING_AMOUNT = Decimal("1.00")


def _cluster_rows_by_amount(rows):
    """Split one payee's (txn_date, amount, currency, account_name) rows into
    amount sub-series (see _AMOUNT_CLUSTER_MAX_STEP_RATIO)."""
    ordered = sorted(rows, key=lambda row: abs(row[1]))
    clusters = []
    current = []
    current_amount = None
    for row in ordered:
        amount = abs(row[1])
        if current and amount > current_amount * _AMOUNT_CLUSTER_MAX_STEP_RATIO:
            clusters.append(current)
            current = []
        current.append(row)
        current_amount = amount
    if current:
        clusters.append(current)
    return clusters


def _dedupe_same_day_rows(rows):
    """Collapse same-day rows in a (date-sorted) amount sub-series to one per
    day -- e.g. a payment that posts to both a checking account and a linked
    credit card on the same date is one billing event, not two, and counting
    it twice would inject a spurious zero-day gap into the interval check."""
    deduped = []
    last_date = None
    for row in rows:
        if row[0] != last_date:
            deduped.append(row)
            last_date = row[0]
    return deduped


# find_merge_groups() buckets by normalized first token before comparing
# names, which keeps it fast for the vast majority of merchants -- but a
# bucket bigger than this (a personal Amazon/eBay/etc. order history can
# easily produce 1000+ distinct payee rows all starting "AMAZON") makes its
# within-bucket pairwise comparison slow for no benefit: that many wildly
# different item descriptions aren't one recurring merchant anyway. Payees
# in an oversized bucket skip fuzzy-merging and just use their own name.
_MERCHANT_MATCH_MAX_BUCKET_SIZE = 250


def _label_payees_by_merchant(payee_names, occurrence_counts):
    """Map each payee_id to a display label, merging near-duplicate payee
    records for the same merchant (store-location codes, order/reference
    numbers, statement noise words like "Advance ") into one label, using
    the same fuzzy clustering as the Dictionaries > Payees merge-suggestion
    feature (see payee_merge.find_merge_groups).
    """
    bucket_sizes = Counter()
    first_tokens = {}
    for payee_id, name in payee_names.items():
        norm = normalize(name)
        first_token = norm.split()[0] if norm else None
        first_tokens[payee_id] = first_token
        if first_token is not None:
            bucket_sizes[first_token] += 1

    labels = {}
    mergeable = {}
    for payee_id, name in payee_names.items():
        first_token = first_tokens[payee_id]
        if first_token is not None and bucket_sizes[first_token] > _MERCHANT_MATCH_MAX_BUCKET_SIZE:
            labels[payee_id] = name
        else:
            mergeable[payee_id] = name

    for group in find_merge_groups(list(mergeable.items()), occurrence_counts):
        for payee_id, _name, _txn_count in group.members:
            labels[payee_id] = group.canonical_name
    for payee_id, name in mergeable.items():
        labels.setdefault(payee_id, name)
    return labels


def compute_recurring_transactions(transactions, start, end, to_usd, min_occurrences=3):
    """Detect recurring/subscription-like spending within [start, end], highest
    estimated monthly cost first.

    `transactions` are (payee_id, payee_name, account_name, txn_date, amount,
    currency) rows, e.g. from data.list_recurring_candidate_transactions()
    (amounts already restricted to spending, i.e. negative). Rows are filtered
    to the date range *before* clustering, both so a merchant's label isn't
    influenced by charges outside the viewed window and so a narrower window
    (see reports_tab's default 3-year lookback) means less name-matching work.
    Payees are then clustered by name similarity (near-duplicate payee records
    for the same merchant count as one series) and, within each, by amount
    (see _cluster_rows_by_amount) since one payee can bill several distinct
    amounts concurrently. Each amount sub-series qualifies on its own when it
    has at least `min_occurrences` charges (same day = one event, see
    _dedupe_same_day_rows) whose gaps are all consistent with one detected
    billing interval (irregular spacing doesn't count, even if the amounts
    match). The estimated monthly cost is annualized from the *most recent*
    charge (not an average), so a price increase is reflected immediately;
    a series priced below _MIN_RECURRING_AMOUNT is dropped as a statement
    rounding/balancing line rather than a real recurring cost.
    """
    in_range = [row for row in transactions if start <= row[3] <= end]

    payee_names = {}
    occurrence_counts = {}
    for payee_id, payee_name, _account_name, _txn_date, _amount, _currency in in_range:
        payee_names.setdefault(payee_id, payee_name)
        occurrence_counts[payee_id] = occurrence_counts.get(payee_id, 0) + 1
    payee_labels = _label_payees_by_merchant(payee_names, occurrence_counts)

    by_label = {}
    for payee_id, _payee_name, account_name, txn_date, amount, currency in in_range:
        label = payee_labels[payee_id]
        by_label.setdefault(label, []).append((txn_date, amount, currency, account_name))

    results = []
    for label, rows in by_label.items():
        for amount_cluster in _cluster_rows_by_amount(rows):
            amount_cluster.sort(key=lambda row: row[0])
            amount_cluster = _dedupe_same_day_rows(amount_cluster)
            if len(amount_cluster) < min_occurrences:
                continue

            dates = [txn_date for txn_date, _amount, _currency, _account_name in amount_cluster]
            gaps = [(dates[i] - dates[i - 1]).days for i in range(1, len(dates))]
            interval_label, periods_per_year = _classify_recurring_interval(gaps)
            if interval_label is None:
                continue

            first_date = dates[0]
            last_date, last_amount, last_currency, last_account = amount_cluster[-1]
            last_amount = abs(last_amount)
            if last_amount < _MIN_RECURRING_AMOUNT:
                continue
            monthly_cost = to_usd(last_currency, last_amount) * Decimal(periods_per_year) / Decimal(12)
            results.append(
                (label, last_account, interval_label, len(amount_cluster), first_date, last_date, monthly_cost)
            )

    return sorted(results, key=lambda row: row[6], reverse=True)


class RecurringSubscriptionsTableModel(QAbstractTableModel):
    COLUMNS = [
        "Payee",
        "Account",
        "Interval",
        "Occurrences",
        "First Charged",
        "Last Charged",
        "Est. Monthly Cost (USD)",
    ]

    def __init__(self, recurring=None, parent=None):
        super().__init__(parent)
        self._recurring = recurring or []

    def set_recurring(self, recurring):
        self.beginResetModel()
        self._recurring = recurring
        self.endResetModel()

    def sort(self, column, order=Qt.AscendingOrder):
        if not self._recurring:
            return
        self.layoutAboutToBeChanged.emit()
        self._recurring.sort(key=lambda item: item[column], reverse=order == Qt.DescendingOrder)
        self.layoutChanged.emit()

    def rowCount(self, parent=None):
        return len(self._recurring)

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
            payee_name,
            account_name,
            interval_label,
            occurrences,
            first_date,
            last_date,
            monthly_cost,
        ) = self._recurring[index.row()]
        values = [
            payee_name,
            account_name,
            interval_label,
            str(occurrences),
            first_date.isoformat(),
            last_date.isoformat(),
            format_currency(monthly_cost),
        ]
        return values[index.column()]


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


def _categorize_accounts_for_assets_and_investments(accounts, to_usd):
    """Split accounts into (investments, assets, loans) lists of (name, value)
    pairs, each sorted by name. Values are converted to USD; loan balances
    are stored negative (debt owed) and are negated here to a positive
    magnitude.
    """
    investments = []
    assets = []
    loans = []
    for _account_id, name, account_type, currency, balance, _is_closed, _is_favorite in accounts:
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
    return investments, assets, loans


def compute_assets_and_investments_breakdown(accounts, to_usd):
    """Per-account breakdown (USD) for the assets and investments report,
    grouped into sections for charting.

    accounts is data.list_accounts()-style rows, as in
    compute_assets_and_investments(). Returns a list of three
    (section_label, [(account_name, value), ...]) pairs, in the order
    Investments, Assets, Loans / Liabilities. Loan values are a positive
    debt magnitude, matching compute_assets_and_investments().
    """
    investments, assets, loans = _categorize_accounts_for_assets_and_investments(accounts, to_usd)
    return [
        ("Investments", investments),
        ("Assets", assets),
        ("Loans / Liabilities", loans),
    ]


def compute_assets_and_investments(accounts, to_usd):
    """Report rows (USD) grouping open accounts into investments, assets,
    and loans/liabilities, each followed by its subtotal, ending with the
    overall total balance (assets + investments - loans).

    accounts is data.list_accounts()-style rows: (account_id, name,
    account_type, currency, balance, is_closed, is_favorite). Loan balances are stored
    negative (debt owed); shown here as a positive value that is subtracted
    from the total.

    Returns a list of (type_label, name, value, emphasized) rows suitable
    for AssetsAndInvestmentsTableModel.set_rows(). Section header rows
    carry the section label in type_label and leave name/value blank;
    account and total rows leave type_label blank and are indented under
    their section by appearing in the name/value columns instead. value
    is None for section header rows.
    """
    investments, assets, loans = _categorize_accounts_for_assets_and_investments(accounts, to_usd)

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


def _rsu_subtotal_row(label, shares_taxed_total, value_total, tax_rate):
    tax = value_total * tax_rate
    net_value = value_total - tax
    return ("", "", label, "", shares_taxed_total, value_total, tax, net_value, True)


def compute_rsu_vesting_forecast(vests, to_usd, tax_rate):
    """Report rows (USD) for the RSU vesting forecast report: one row per
    upcoming vest event sorted by date, followed by a bold subtotal row
    after each calendar year's vests and a final bold grand-total row.

    vests is data.list_upcoming_vests()-style rows: (account_name,
    security_name, vest_date, quantity, price, currency). tax_rate is a
    Decimal fraction (e.g. Decimal("0.35") for 35%) applied to each vest's
    estimated value to get an estimated tax owed and the resulting
    net-of-tax value, and to its share count to get shares_taxed -- the
    number of vesting shares expected to be withheld/sold to cover that
    tax. shares_taxed doesn't depend on price, so it's shown even when the
    security has no priced trade yet; price is None in that case, so the
    dollar value/tax/net_value are also None and excluded from the
    subtotals (rather than treated as zero).

    Returns a list of (vest_date, account_name, security_name, quantity,
    shares_taxed, value, tax, net_value, emphasized) rows suitable for
    RsuVestingForecastTableModel.set_rows(). Subtotal/total rows leave
    vest_date/account_name/quantity blank and carry their label in
    security_name instead.
    """
    if not vests:
        return []

    ordered = sorted(vests, key=lambda row: (row[2], row[0], row[1]))

    rows = []
    year_value_total = Decimal("0")
    year_shares_taxed_total = Decimal("0")
    grand_value_total = Decimal("0")
    grand_shares_taxed_total = Decimal("0")
    current_year = ordered[0][2].year
    for account_name, security_name, vest_date, quantity, price, currency in ordered:
        if vest_date.year != current_year:
            rows.append(
                _rsu_subtotal_row(f"Total {current_year}", year_shares_taxed_total, year_value_total, tax_rate)
            )
            year_value_total = Decimal("0")
            year_shares_taxed_total = Decimal("0")
            current_year = vest_date.year
        shares_taxed = quantity * tax_rate
        year_shares_taxed_total += shares_taxed
        grand_shares_taxed_total += shares_taxed
        if price is not None:
            value = to_usd(currency, quantity * price)
            tax = value * tax_rate
            net_value = value - tax
            year_value_total += value
            grand_value_total += value
        else:
            value = tax = net_value = None
        rows.append((vest_date, account_name, security_name, quantity, shares_taxed, value, tax, net_value, False))
    rows.append(_rsu_subtotal_row(f"Total {current_year}", year_shares_taxed_total, year_value_total, tax_rate))
    rows.append(_rsu_subtotal_row("Total", grand_shares_taxed_total, grand_value_total, tax_rate))
    return rows


def compute_rsu_vesting_cumulative_series(vests, to_usd, tax_rate):
    """Cumulative shares, shares taxed, estimated USD value, and tax owed
    as of each upcoming vest date, for the RSU vesting forecast chart.

    vests is data.list_upcoming_vests()-style rows, and tax_rate a Decimal
    fraction, as in compute_rsu_vesting_forecast(). Returns (shares_series,
    shares_taxed_series, value_series, tax_series), each a list of
    (vest_date, cumulative) pairs in chronological order. A vest with no
    known price still adds to the shares and shares_taxed running totals
    (shares_taxed = quantity * tax_rate doesn't depend on price) but not
    the value or tax ones (their price is unknown, not zero).
    """
    ordered = sorted(vests, key=lambda row: (row[2], row[0], row[1]))

    shares_series = []
    shares_taxed_series = []
    value_series = []
    tax_series = []
    cumulative_shares = Decimal("0")
    cumulative_shares_taxed = Decimal("0")
    cumulative_value = Decimal("0")
    cumulative_tax = Decimal("0")
    for account_name, security_name, vest_date, quantity, price, currency in ordered:
        cumulative_shares += quantity
        cumulative_shares_taxed += quantity * tax_rate
        if price is not None:
            value = to_usd(currency, quantity * price)
            cumulative_value += value
            cumulative_tax += value * tax_rate
        shares_series.append((vest_date, cumulative_shares))
        shares_taxed_series.append((vest_date, cumulative_shares_taxed))
        value_series.append((vest_date, cumulative_value))
        tax_series.append((vest_date, cumulative_tax))
    return shares_series, shares_taxed_series, value_series, tax_series


class RsuVestingForecastTableModel(QAbstractTableModel):
    COLUMNS = [
        "Vest Date", "Account", "Security", "Shares", "Shares Taxed",
        "Est. Value (USD)", "Est. Tax (USD)", "Net of Tax (USD)",
    ]

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
        (
            vest_date, account_name, security_name, quantity, shares_taxed, value, tax, net_value, emphasized,
        ) = self._rows[index.row()]
        if role == Qt.DisplayRole:
            column = index.column()
            if column == 0:
                return vest_date.isoformat() if vest_date else ""
            if column == 1:
                return account_name
            if column == 2:
                return security_name
            if column == 3:
                return format_quantity(quantity) if quantity != "" else ""
            if column == 4:
                return format_quantity(shares_taxed) if shares_taxed != "" else ""
            if column == 5:
                return format_currency(value) if value is not None else ""
            if column == 6:
                return format_currency(tax) if tax is not None else ""
            return format_currency(net_value) if net_value is not None else ""
        if role == Qt.FontRole and emphasized:
            font = QFont()
            font.setBold(True)
            return font
        return None


class ProjectionTableModel(QAbstractTableModel):
    COLUMNS = [
        "Year", "Age", "Retired", "Income (USD)", "Social Security (USD)", "Tax (USD)",
        "Base Spending (USD)", "Medical Costs (USD)", "Total Spending (USD)",
        "Net Cash Flow (USD)", "Assets (USD)", "Investments (USD)", "Total Net Worth (USD)",
    ]

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
        if role != Qt.DisplayRole:
            return None
        (
            year, age, retired, income, social_security, tax, base_spending, medical_cost,
            total_spending, net_cash_flow, assets, investments, total_net_worth,
        ) = self._rows[index.row()]
        column = index.column()
        if column == 0:
            return str(year)
        if column == 1:
            return str(age)
        if column == 2:
            return "Yes" if retired else "No"
        if column == 3:
            return format_currency(income)
        if column == 4:
            return format_currency(social_security)
        if column == 5:
            return format_currency(tax)
        if column == 6:
            return format_currency(base_spending)
        if column == 7:
            return format_currency(medical_cost)
        if column == 8:
            return format_currency(total_spending)
        if column == 9:
            return format_currency(net_cash_flow)
        if column == 10:
            return format_currency(assets)
        if column == 11:
            return format_currency(investments)
        return format_currency(total_net_worth)


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
                for _, _, _, currency, balance, is_closed, _is_favorite in self._accounts
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
        _, name, account_type, currency, balance, is_closed, is_favorite = self._accounts[
            index.row()
        ]
        if role == Qt.BackgroundRole:
            if is_favorite:
                return FAVORITE_BACKGROUND_DARK if theme.is_dark() else FAVORITE_BACKGROUND_LIGHT
            return None
        if role != Qt.DisplayRole:
            return None
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

    def __init__(self, transactions=None, parent=None, is_investment=False, is_loan=False, highlighted_ids=None):
        super().__init__(parent)
        self._transactions = transactions or []
        self._is_investment = is_investment
        self._is_loan = is_loan
        self._highlighted_ids = set(highlighted_ids or ())

    def set_transactions(self, transactions, is_investment=False, is_loan=False, highlighted_ids=None):
        self.beginResetModel()
        self._transactions = transactions
        self._is_investment = is_investment
        self._is_loan = is_loan
        self._highlighted_ids = set(highlighted_ids or ())
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
        old_persistent_indexes = self.persistentIndexList()
        # Transaction rows aren't reused or copied by sorting, so the row
        # object's identity (not its transaction id, which loan interest
        # rows share as None) reliably tracks each row to its new position.
        old_rows = [self._transactions[index.row()] for index in old_persistent_indexes]

        known = [row for row in self._transactions if row[field_index] is not None]
        unknown = [row for row in self._transactions if row[field_index] is None]
        known.sort(key=lambda row: row[field_index], reverse=(order == Qt.DescendingOrder))
        self._transactions = known + unknown

        new_row_by_identity = {id(row): new_row for new_row, row in enumerate(self._transactions)}
        new_persistent_indexes = [
            self.index(new_row_by_identity[id(row)], index.column())
            for row, index in zip(old_rows, old_persistent_indexes)
        ]
        self.changePersistentIndexList(old_persistent_indexes, new_persistent_indexes)
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
        if role == Qt.BackgroundRole:
            transaction_id = self._transactions[index.row()][0]
            if transaction_id in self._highlighted_ids:
                return IMPORTED_BACKGROUND_DARK if theme.is_dark() else IMPORTED_BACKGROUND_LIGHT
            return None
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
