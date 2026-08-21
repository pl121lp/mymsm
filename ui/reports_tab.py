"""Reports tab: browse canned reports, e.g. net worth over time."""

from decimal import Decimal

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
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


def _to_qdate(python_date):
    return QDate(python_date.year, python_date.month, python_date.day)


class ReportsPane(QWidget):
    def __init__(self, conn, report_error, to_usd, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._report_error = report_error
        self._to_usd = to_usd
        self._net_worth_accounts = []

        self.list_model = DictionaryListModel(REPORTS)
        self.list_view = QListView()
        self.list_view.setModel(self.list_model)
        self.list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_view.selectionModel().selectionChanged.connect(self._on_selected)
        enable_cell_copy(self.list_view)

        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.Antialiasing)

        self.range_label = QLabel()

        self.start_date_edit = QDateEdit()
        self.start_date_edit.setCalendarPopup(True)
        self.end_date_edit = QDateEdit()
        self.end_date_edit.setCalendarPopup(True)
        self.update_range_button = QPushButton("Update")
        self.update_range_button.clicked.connect(self._on_range_updated)

        range_row = QHBoxLayout()
        range_row.addWidget(QLabel("From:"))
        range_row.addWidget(self.start_date_edit)
        range_row.addWidget(QLabel("To:"))
        range_row.addWidget(self.end_date_edit)
        range_row.addWidget(self.update_range_button)
        range_row.addStretch()

        chart_panel = QWidget()
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.addWidget(self.chart_view)
        chart_layout.addWidget(self.range_label)
        chart_layout.addLayout(range_row)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self.list_view)
        splitter.addWidget(chart_panel)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

    def _on_selected(self, selected=None, deselected=None):
        indexes = self.list_view.selectionModel().selectedIndexes()
        if not indexes:
            self.chart_view.setChart(QChart())
            self.range_label.setText("")
            return
        report_id = self.list_model.id_at(indexes[0].row())
        if report_id == NET_WORTH_REPORT_ID:
            self._load_net_worth_report()

    def _load_net_worth_report(self):
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
            self._net_worth_accounts = []
            self.chart_view.setChart(QChart())
            self.range_label.setText("")
            self._report_error("No transactions available for net worth report.")
            return

        self._net_worth_accounts = account_series

        self.start_date_edit.blockSignals(True)
        self.end_date_edit.blockSignals(True)
        self.start_date_edit.setDate(_to_qdate(earliest))
        self.end_date_edit.setDate(_to_qdate(latest))
        self.start_date_edit.blockSignals(False)
        self.end_date_edit.blockSignals(False)

        self._render_net_worth_chart(earliest, latest)

    def _on_range_updated(self):
        if not self._net_worth_accounts:
            return
        start = self.start_date_edit.date().toPython()
        end = self.end_date_edit.date().toPython()
        if start > end:
            self._report_error("Start date must be on or before end date.")
            return
        self._render_net_worth_chart(start, end)

    def _render_net_worth_chart(self, start, end):
        sample_dates = generate_sample_dates(start, end)
        series = compute_net_worth_series(self._net_worth_accounts, sample_dates, self._to_usd)
        categories = [sample_date.isoformat() for sample_date, _ in series]
        values = [total for _, total in series]
        chart = build_bar_chart("Net Worth Over Time (USD)", categories, values)
        self.chart_view.setChart(chart)
        self.range_label.setText(f"Showing {start.isoformat()} to {end.isoformat()}")
