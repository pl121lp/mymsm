"""Reports tab: browse canned reports, e.g. net worth over time."""

from decimal import Decimal

from PySide6.QtCore import Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QListView,
    QSplitter,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCharts import QChart, QChartView

import data
from charts import build_bar_chart
from data import INVESTMENT_ACCOUNT_TYPE
from models import (
    DictionaryListModel,
    compute_account_value_history,
    compute_net_worth_series,
    generate_sample_dates,
)
from table_copy import enable_cell_copy

NET_WORTH_REPORT_ID = "net_worth_over_time"
REPORTS = [(NET_WORTH_REPORT_ID, "Net worth over time")]


class ReportsPane(QWidget):
    def __init__(self, conn, report_error, to_usd, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._report_error = report_error
        self._to_usd = to_usd

        self.list_model = DictionaryListModel(REPORTS)
        self.list_view = QListView()
        self.list_view.setModel(self.list_model)
        self.list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_view.selectionModel().selectionChanged.connect(self._on_selected)
        enable_cell_copy(self.list_view)

        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.Antialiasing)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.list_view)
        splitter.addWidget(self.chart_view)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

    def _on_selected(self, selected=None, deselected=None):
        indexes = self.list_view.selectionModel().selectedIndexes()
        if not indexes:
            self.chart_view.setChart(QChart())
            return
        report_id = self.list_model.id_at(indexes[0].row())
        if report_id == NET_WORTH_REPORT_ID:
            self._show_net_worth_report()

    def _show_net_worth_report(self):
        try:
            accounts = data.list_accounts(self._conn, include_closed=True)
        except Exception as exc:
            self._report_error(f"Failed to load net worth report: {exc}")
            return

        account_series = []
        earliest = latest = None
        for account_id, _name, account_type, currency, _balance, _is_closed in accounts:
            is_investment = account_type == INVESTMENT_ACCOUNT_TYPE
            opening_balance = data.get_opening_balance(self._conn, account_id)
            try:
                transactions = data.list_transactions(self._conn, account_id)
            except Exception as exc:
                self._report_error(f"Failed to load net worth report: {exc}")
                return
            history = compute_account_value_history(transactions, opening_balance, is_investment)
            initial_value = Decimal("0") if is_investment else (opening_balance or Decimal("0"))
            account_series.append((currency, initial_value, history))
            if history:
                earliest = history[0][0] if earliest is None else min(earliest, history[0][0])
                latest = history[-1][0] if latest is None else max(latest, history[-1][0])

        if earliest is None:
            self.chart_view.setChart(QChart())
            self._report_error("No transactions available for net worth report.")
            return

        sample_dates = generate_sample_dates(earliest, latest)
        series = compute_net_worth_series(account_series, sample_dates, self._to_usd)
        categories = [sample_date.isoformat() for sample_date, _ in series]
        values = [total for _, total in series]
        chart = build_bar_chart("Net Worth Over Time (USD)", categories, values)
        self.chart_view.setChart(chart)
