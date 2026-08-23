"""Reports tab: browse canned reports, e.g. net worth over time."""

from decimal import Decimal
from functools import partial

from PySide6.QtCore import QDate, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QDateEdit,
    QDialog,
    QHBoxLayout,
    QLabel,
    QListView,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCharts import QChart, QChartView

import data
from category_filter_dialog import CategoryFilterDialog
from category_transactions_dialog import CategoryTransactionsDialog
from charts import build_bar_chart, build_pie_chart
from data import INVESTMENT_ACCOUNT_TYPE
from models import (
    DictionaryListModel,
    IncomeByCategoryTableModel,
    SpendingByCategoryTableModel,
    compute_account_value_history,
    compute_income_by_category,
    compute_net_worth_series,
    compute_spending_by_category,
    generate_sample_dates,
)
from table_copy import enable_cell_copy

NET_WORTH_REPORT_ID = "net_worth_over_time"
SPENDING_BY_CATEGORY_REPORT_ID = "spending_by_category"
INCOME_BY_CATEGORY_REPORT_ID = "income_by_category"
REPORTS = [
    (NET_WORTH_REPORT_ID, "Net worth over time"),
    (SPENDING_BY_CATEGORY_REPORT_ID, "Spending by category"),
    (INCOME_BY_CATEGORY_REPORT_ID, "Income by category"),
]


def _to_qdate(python_date):
    return QDate(python_date.year, python_date.month, python_date.day)


class ReportsPane(QWidget):
    def __init__(self, conn, report_error, to_usd, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._report_error = report_error
        self._to_usd = to_usd
        self._active_report_id = None
        self._net_worth_accounts = []
        self._category_transactions = []
        self._category_totals = []
        self._selected_categories = None

        self.list_model = DictionaryListModel(REPORTS)
        self.list_view = QListView()
        self.list_view.setModel(self.list_model)
        self.list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_view.selectionModel().selectionChanged.connect(self._on_selected)
        enable_cell_copy(self.list_view)

        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.Antialiasing)

        self.spending_table_model = SpendingByCategoryTableModel()
        self.income_table_model = IncomeByCategoryTableModel()
        self.category_table_view = QTableView()
        self.category_table_view.setModel(self.spending_table_model)
        self.category_table_view.horizontalHeader().setStretchLastSection(True)
        self.category_table_view.setVisible(False)
        self.category_table_view.doubleClicked.connect(self._on_category_table_double_clicked)
        enable_cell_copy(self.category_table_view, extra_actions=self._category_table_context_actions)

        self._category_reports = {
            SPENDING_BY_CATEGORY_REPORT_ID: {
                "compute": compute_spending_by_category,
                "model": self.spending_table_model,
                "pie_title": "Spending by Category (USD)",
                "noun": "spending",
            },
            INCOME_BY_CATEGORY_REPORT_ID: {
                "compute": compute_income_by_category,
                "model": self.income_table_model,
                "pie_title": "Income by Category (USD)",
                "noun": "income",
            },
        }

        self.view_selector = QComboBox()
        self.view_selector.addItems(["Table", "Pie Chart"])
        self.view_selector.currentIndexChanged.connect(self._on_view_mode_changed)
        self.custom_categories_button = QPushButton("Custom Categories")
        self.custom_categories_button.clicked.connect(self._on_custom_categories_clicked)
        self.view_selector_row = QWidget()
        view_selector_row_layout = QHBoxLayout(self.view_selector_row)
        view_selector_row_layout.setContentsMargins(0, 0, 0, 0)
        view_selector_row_layout.addWidget(QLabel("View:"))
        view_selector_row_layout.addWidget(self.view_selector)
        view_selector_row_layout.addWidget(self.custom_categories_button)
        view_selector_row_layout.addStretch()
        self.view_selector_row.setVisible(False)

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
        chart_layout.addWidget(self.category_table_view)
        chart_layout.addWidget(self.view_selector_row)
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
            self._active_report_id = None
            self.chart_view.setChart(QChart())
            self.spending_table_model.set_categories([])
            self.income_table_model.set_categories([])
            self.range_label.setText("")
            self.view_selector_row.setVisible(False)
            return
        report_id = self.list_model.id_at(indexes[0].row())
        self._active_report_id = report_id
        is_category_report = report_id in self._category_reports
        self.view_selector_row.setVisible(is_category_report)
        if is_category_report:
            self.view_selector.blockSignals(True)
            self.view_selector.setCurrentIndex(0)
            self.view_selector.blockSignals(False)
            self.category_table_view.setModel(self._category_reports[report_id]["model"])
        self.chart_view.setVisible(report_id == NET_WORTH_REPORT_ID)
        self.category_table_view.setVisible(is_category_report)
        if report_id == NET_WORTH_REPORT_ID:
            self._load_net_worth_report()
        elif is_category_report:
            self._load_category_report(report_id)

    def _on_view_mode_changed(self):
        if self._active_report_id not in self._category_reports:
            return
        is_pie_chart = self.view_selector.currentText() == "Pie Chart"
        self.chart_view.setVisible(is_pie_chart)
        self.category_table_view.setVisible(not is_pie_chart)
        if is_pie_chart:
            self._render_pie_chart()

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
        if self._active_report_id == NET_WORTH_REPORT_ID:
            if not self._net_worth_accounts:
                return
            start = self.start_date_edit.date().toPython()
            end = self.end_date_edit.date().toPython()
            if start > end:
                self._report_error("Start date must be on or before end date.")
                return
            self._render_net_worth_chart(start, end)
        elif self._active_report_id in self._category_reports:
            start = self.start_date_edit.date().toPython()
            end = self.end_date_edit.date().toPython()
            if start > end:
                self._report_error("Start date must be on or before end date.")
                return
            self._render_category_table(start, end)

    def _render_net_worth_chart(self, start, end):
        sample_dates = generate_sample_dates(start, end)
        series = compute_net_worth_series(self._net_worth_accounts, sample_dates, self._to_usd)
        categories = [sample_date.isoformat() for sample_date, _ in series]
        values = [total for _, total in series]
        chart = build_bar_chart("Net Worth Over Time (USD)", categories, values)
        self.chart_view.setChart(chart)
        self.range_label.setText(f"Showing {start.isoformat()} to {end.isoformat()}")

    def _load_category_report(self, report_id):
        self._selected_categories = None
        noun = self._category_reports[report_id]["noun"]
        try:
            transactions = data.list_category_spending(self._conn)
        except Exception as exc:
            self._report_error(f"Failed to load {noun} by category report: {exc}")
            return

        if not transactions:
            self._category_transactions = []
            self._category_reports[report_id]["model"].set_categories([])
            self.range_label.setText("")
            self._report_error(f"No categorized transactions available for {noun} report.")
            return

        self._category_transactions = transactions
        earliest = min(txn_date for _, _, txn_date, _, _ in transactions)
        latest = max(txn_date for _, _, txn_date, _, _ in transactions)

        self.start_date_edit.blockSignals(True)
        self.end_date_edit.blockSignals(True)
        self.start_date_edit.setDate(_to_qdate(earliest))
        self.end_date_edit.setDate(_to_qdate(latest))
        self.start_date_edit.blockSignals(False)
        self.end_date_edit.blockSignals(False)

        self._render_category_table(earliest, latest)

    def _render_category_table(self, start, end):
        config = self._category_reports[self._active_report_id]
        categories = config["compute"](self._category_transactions, start, end, self._to_usd)
        if self._selected_categories is not None:
            categories = [
                (name, total) for name, total in categories if name in self._selected_categories
            ]
        self._category_totals = categories
        config["model"].set_categories(categories)
        self.range_label.setText(f"Showing {start.isoformat()} to {end.isoformat()}")
        if self.view_selector.currentText() == "Pie Chart":
            self._render_pie_chart()

    def _render_pie_chart(self):
        pie_title = self._category_reports[self._active_report_id]["pie_title"]
        chart = build_pie_chart(pie_title, self._category_totals)
        self.chart_view.setChart(chart)

    def _on_custom_categories_clicked(self):
        all_names = sorted({name for _cid, name, _date, _amt, _cur in self._category_transactions})
        current_selection = (
            self._selected_categories if self._selected_categories is not None else set(all_names)
        )
        dialog = CategoryFilterDialog(all_names, current_selection, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self._selected_categories = dialog.selected_categories()
        start = self.start_date_edit.date().toPython()
        end = self.end_date_edit.date().toPython()
        self._render_category_table(start, end)

    def _on_category_table_double_clicked(self, index):
        if index.column() != 0:
            return
        self._show_category_transactions(index.row())

    def _category_table_context_actions(self, row):
        return [("Show Transactions", partial(self._show_category_transactions, row))]

    def _show_category_transactions(self, row):
        config = self._category_reports[self._active_report_id]
        category_name, _total = config["model"].category_at(row)
        category_id = self._category_id_for_name(category_name)
        if category_id is None:
            return
        try:
            transactions = data.list_category_transactions(self._conn, category_id)
        except Exception as exc:
            self._report_error(f"Failed to load transactions for {category_name}: {exc}")
            return
        dialog = CategoryTransactionsDialog(category_name, transactions, parent=self)
        dialog.exec()

    def _category_id_for_name(self, category_name):
        for category_id, name, _txn_date, _amount, _currency in self._category_transactions:
            if name == category_name:
                return category_id
        return None
