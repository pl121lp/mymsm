"""Reports tab: browse canned reports, e.g. net worth over time."""

from datetime import date
from decimal import Decimal
from functools import partial

from PySide6.QtCore import QDate, Qt, QTimer
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
    QScrollArea,
    QSizePolicy,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtCharts import QChart, QChartView

import data
from busy_indicator import BusyIndicator, run_in_background
from category_filter_dialog import CategoryFilterDialog, InvestmentFilterDialog
from category_transactions_dialog import CategoryTransactionsDialog
from charts import (
    build_bar_chart,
    build_grouped_stacked_bar_chart,
    build_line_chart,
    build_pie_chart,
    build_stacked_area_chart,
)
from data import ASSET_ACCOUNT_TYPE, INVESTMENT_ACCOUNT_TYPE
from college_tuition import CollegeTuitionInputs, PersonCollegeCosts, compute_college_tuition_projection
from college_tuition_controls import CollegeTuitionControlsPanel, default_college_tuition_values
from college_tuition_settings import load_college_tuition_settings, save_college_tuition_settings
from dateutils import add_months
from models import (
    AssetsAndInvestmentsTableModel,
    DictionaryListModel,
    IncomeByCategoryTableModel,
    InvestmentAnalysisTableModel,
    RecurringSubscriptionsTableModel,
    RsuVestingForecastTableModel,
    SpendingByCategoryTableModel,
    compute_account_value_history,
    compute_assets_and_investments,
    compute_assets_and_investments_breakdown,
    compute_income_by_category,
    compute_investment_analysis,
    compute_net_worth_series,
    compute_recurring_transactions,
    compute_rsu_vesting_cumulative_series,
    compute_rsu_vesting_forecast,
    compute_spending_by_category,
    generate_sample_dates,
)
import theme
from form_controls import percent_spinbox
from projection import ProjectionInputs, compute_projection
from projection_controls import ProjectionControlsPanel, default_projection_values
from projection_settings import load_projection_settings, save_projection_settings
from rsu_tax_settings import load_rsu_tax_settings, save_rsu_tax_settings
from table_copy import enable_cell_copy

RSU_DEFAULT_TAX_RATE = 35.0

NET_WORTH_REPORT_ID = "net_worth_over_time"
SPENDING_BY_CATEGORY_REPORT_ID = "spending_by_category"
INCOME_BY_CATEGORY_REPORT_ID = "income_by_category"
INVESTMENT_ANALYSIS_REPORT_ID = "investment_analysis"
NET_WORTH_PROJECTION_REPORT_ID = "net_worth_projection"
COLLEGE_TUITION_PROJECTION_REPORT_ID = "college_tuition_projection"
ASSETS_AND_INVESTMENTS_REPORT_ID = "assets_and_investments"
RECURRING_SUBSCRIPTIONS_REPORT_ID = "recurring_subscriptions"
RSU_VESTING_FORECAST_REPORT_ID = "rsu_vesting_forecast"
REPORTS = [
    (NET_WORTH_REPORT_ID, "Net worth over time"),
    (SPENDING_BY_CATEGORY_REPORT_ID, "Spending by category"),
    (INCOME_BY_CATEGORY_REPORT_ID, "Income by category"),
    (INVESTMENT_ANALYSIS_REPORT_ID, "Investment analysis"),
    (NET_WORTH_PROJECTION_REPORT_ID, "Net Worth Projection"),
    (COLLEGE_TUITION_PROJECTION_REPORT_ID, "College Tuition Projection"),
    (ASSETS_AND_INVESTMENTS_REPORT_ID, "Assets and investments"),
    (RECURRING_SUBSCRIPTIONS_REPORT_ID, "Recurring / Subscriptions"),
    (RSU_VESTING_FORECAST_REPORT_ID, "RSU Vesting Forecast"),
]


# Detecting recurring charges means fuzzy-matching every payee name against
# every other one in the window (see models.compute_recurring_transactions),
# so defaulting to the full transaction history can make an account with
# years of QFX imports painfully slow to open. 3 years back covers the
# billing cycles this report cares about (even annual subscriptions) while
# keeping that candidate set small; the From date can still be widened by
# hand for a full-history look.
RECURRING_DEFAULT_LOOKBACK_MONTHS = 36


def _today():
    return date.today()


def _to_qdate(python_date):
    return QDate(python_date.year, python_date.month, python_date.day)


def _empty_chart():
    chart = QChart()
    chart.setTheme(theme.chart_theme())
    return chart


class ReportsPane(QWidget):
    def __init__(self, conn, report_error, to_usd, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._report_error = report_error
        self._to_usd = to_usd
        self._active_report_id = None
        self._net_worth_accounts = []
        self._net_worth_worker = None
        self._category_transactions = []
        self._category_totals = []
        self._selected_categories = None
        self._investment_prices = []
        self._selected_investments = None
        self._projection_asset_values = {}
        self._assets_investments_breakdown = []
        self._recurring_transactions = []
        self._recurring_worker = None
        self._rsu_vests = []

        self.list_model = DictionaryListModel(REPORTS)
        self.list_view = QListView()
        self.list_view.setModel(self.list_model)
        self.list_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_view.selectionModel().selectionChanged.connect(self._on_selected)
        enable_cell_copy(self.list_view)

        self.chart_view = QChartView()
        self.chart_view.setRenderHint(QPainter.Antialiasing)
        self.chart_view.setChart(_empty_chart())

        self.net_worth_busy_indicator = BusyIndicator()
        self.net_worth_status_row = QWidget()
        net_worth_status_layout = QHBoxLayout(self.net_worth_status_row)
        net_worth_status_layout.setContentsMargins(0, 0, 0, 0)
        net_worth_status_layout.addWidget(self.net_worth_busy_indicator)
        net_worth_status_layout.addWidget(QLabel("Loading net worth report…"))
        net_worth_status_layout.addStretch()
        self.net_worth_status_row.setVisible(False)

        self.spending_table_model = SpendingByCategoryTableModel()
        self.income_table_model = IncomeByCategoryTableModel()
        self.category_table_view = QTableView()
        self.category_table_view.setModel(self.spending_table_model)
        self.category_table_view.horizontalHeader().setStretchLastSection(True)
        self.category_table_view.setVisible(False)
        self.category_table_view.doubleClicked.connect(self._on_category_table_double_clicked)
        enable_cell_copy(self.category_table_view, extra_actions=self._category_table_context_actions)

        self.investment_table_model = InvestmentAnalysisTableModel()
        self.investment_table_view = QTableView()
        self.investment_table_view.setModel(self.investment_table_model)
        self.investment_table_view.horizontalHeader().setStretchLastSection(True)
        self.investment_table_view.setSortingEnabled(True)
        self.investment_table_view.setVisible(False)
        enable_cell_copy(self.investment_table_view)

        self.custom_investments_button = QPushButton("Custom Investments")
        self.custom_investments_button.clicked.connect(self._on_custom_investments_clicked)
        self.investment_controls_row = QWidget()
        investment_controls_layout = QHBoxLayout(self.investment_controls_row)
        investment_controls_layout.setContentsMargins(0, 0, 0, 0)
        investment_controls_layout.addWidget(self.custom_investments_button)
        investment_controls_layout.addStretch()
        self.investment_controls_row.setVisible(False)

        self.projection_controls = ProjectionControlsPanel()
        self.projection_controls.updated.connect(self._on_projection_updated)

        # Wrapped in a scroll area so the (tall) controls panel scrolls
        # internally instead of pushing the chart down; Ignored vertical size
        # policy means the layout allocates space by stretch factor below,
        # not by this scroll area's content sizeHint.
        self.projection_controls_scroll_area = QScrollArea()
        self.projection_controls_scroll_area.setWidgetResizable(True)
        self.projection_controls_scroll_area.setWidget(self.projection_controls)
        self.projection_controls_scroll_area.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Ignored
        )
        self.projection_controls_scroll_area.setVisible(False)

        self.college_tuition_controls = CollegeTuitionControlsPanel()
        self.college_tuition_controls.updated.connect(self._on_college_tuition_updated)

        self.college_tuition_controls_scroll_area = QScrollArea()
        self.college_tuition_controls_scroll_area.setWidgetResizable(True)
        self.college_tuition_controls_scroll_area.setWidget(self.college_tuition_controls)
        self.college_tuition_controls_scroll_area.setSizePolicy(
            QSizePolicy.Expanding, QSizePolicy.Ignored
        )
        self.college_tuition_controls_scroll_area.setVisible(False)

        self.assets_investments_table_model = AssetsAndInvestmentsTableModel()
        self.assets_investments_table_view = QTableView()
        self.assets_investments_table_view.setModel(self.assets_investments_table_model)
        self.assets_investments_table_view.horizontalHeader().setStretchLastSection(True)
        self.assets_investments_table_view.setVisible(False)
        enable_cell_copy(self.assets_investments_table_view)

        self.assets_investments_bar_chart_view = QChartView()
        self.assets_investments_bar_chart_view.setRenderHint(QPainter.Antialiasing)
        self.assets_investments_bar_chart_view.setChart(_empty_chart())
        self.assets_investments_bar_chart_view.setVisible(False)

        self.assets_investments_pie_charts = {}
        self.assets_investments_pies_panel = QWidget()
        pies_layout = QHBoxLayout(self.assets_investments_pies_panel)
        pies_layout.setContentsMargins(0, 0, 0, 0)
        for section_label in ("Investments", "Assets", "Loans / Liabilities"):
            pie_chart_view = QChartView()
            pie_chart_view.setRenderHint(QPainter.Antialiasing)
            pie_chart_view.setChart(_empty_chart())
            self.assets_investments_pie_charts[section_label] = pie_chart_view
            pies_layout.addWidget(pie_chart_view)
        self.assets_investments_pies_panel.setVisible(False)

        self.recurring_table_model = RecurringSubscriptionsTableModel()
        self.recurring_table_view = QTableView()
        self.recurring_table_view.setModel(self.recurring_table_model)
        self.recurring_table_view.horizontalHeader().setStretchLastSection(True)
        self.recurring_table_view.setSortingEnabled(True)
        self.recurring_table_view.setVisible(False)
        enable_cell_copy(self.recurring_table_view)

        self.rsu_vesting_forecast_table_model = RsuVestingForecastTableModel()
        self.rsu_vesting_forecast_table_view = QTableView()
        self.rsu_vesting_forecast_table_view.setModel(self.rsu_vesting_forecast_table_model)
        self.rsu_vesting_forecast_table_view.horizontalHeader().setStretchLastSection(True)
        self.rsu_vesting_forecast_table_view.setVisible(False)
        enable_cell_copy(self.rsu_vesting_forecast_table_view)

        self.rsu_vesting_shares_chart_view = QChartView()
        self.rsu_vesting_shares_chart_view.setRenderHint(QPainter.Antialiasing)
        self.rsu_vesting_shares_chart_view.setChart(_empty_chart())
        self.rsu_vesting_value_chart_view = QChartView()
        self.rsu_vesting_value_chart_view.setRenderHint(QPainter.Antialiasing)
        self.rsu_vesting_value_chart_view.setChart(_empty_chart())
        self.rsu_vesting_charts_panel = QWidget()
        rsu_vesting_charts_layout = QVBoxLayout(self.rsu_vesting_charts_panel)
        rsu_vesting_charts_layout.setContentsMargins(0, 0, 0, 0)
        rsu_vesting_charts_layout.addWidget(self.rsu_vesting_shares_chart_view)
        rsu_vesting_charts_layout.addWidget(self.rsu_vesting_value_chart_view)
        self.rsu_vesting_charts_panel.setVisible(False)

        self.rsu_vesting_tax_rate_spinbox = percent_spinbox(RSU_DEFAULT_TAX_RATE)
        self.rsu_vesting_tax_rate_spinbox.valueChanged.connect(self._on_rsu_vesting_tax_rate_changed)
        self.rsu_vesting_controls_row = QWidget()
        rsu_vesting_controls_layout = QHBoxLayout(self.rsu_vesting_controls_row)
        rsu_vesting_controls_layout.setContentsMargins(0, 0, 0, 0)
        rsu_vesting_controls_layout.addWidget(QLabel("Tax Rate:"))
        rsu_vesting_controls_layout.addWidget(self.rsu_vesting_tax_rate_spinbox)
        rsu_vesting_controls_layout.addStretch()
        self.rsu_vesting_controls_row.setVisible(False)

        self.recurring_busy_indicator = BusyIndicator()
        self.recurring_status_row = QWidget()
        recurring_status_layout = QHBoxLayout(self.recurring_status_row)
        recurring_status_layout.setContentsMargins(0, 0, 0, 0)
        recurring_status_layout.addWidget(self.recurring_busy_indicator)
        recurring_status_layout.addWidget(QLabel("Detecting recurring charges…"))
        recurring_status_layout.addStretch()
        self.recurring_status_row.setVisible(False)

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
        self.range_controls_row = QWidget()
        self.range_controls_row.setLayout(range_row)

        chart_panel = QWidget()
        chart_layout = QVBoxLayout(chart_panel)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.addWidget(self.net_worth_status_row)
        chart_layout.addWidget(self.chart_view, 1)
        chart_layout.addWidget(self.category_table_view)
        chart_layout.addWidget(self.investment_table_view)
        chart_layout.addWidget(self.assets_investments_table_view)
        chart_layout.addWidget(self.recurring_status_row)
        chart_layout.addWidget(self.recurring_table_view)
        chart_layout.addWidget(self.rsu_vesting_forecast_table_view)
        chart_layout.addWidget(self.rsu_vesting_charts_panel, 1)
        chart_layout.addWidget(self.assets_investments_bar_chart_view, 1)
        chart_layout.addWidget(self.assets_investments_pies_panel, 1)
        chart_layout.addWidget(self.investment_controls_row)
        chart_layout.addWidget(self.rsu_vesting_controls_row)
        chart_layout.addWidget(self.view_selector_row)
        chart_layout.addWidget(self.projection_controls_scroll_area, 1)
        chart_layout.addWidget(self.college_tuition_controls_scroll_area, 1)
        chart_layout.addWidget(self.range_label)
        chart_layout.addWidget(self.range_controls_row)

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
            self.chart_view.setChart(_empty_chart())
            self.net_worth_status_row.setVisible(False)
            self.spending_table_model.set_categories([])
            self.income_table_model.set_categories([])
            self.investment_table_model.set_investments([])
            self.assets_investments_table_model.set_rows([])
            self.recurring_table_model.set_recurring([])
            self.rsu_vesting_forecast_table_model.set_rows([])
            self.recurring_status_row.setVisible(False)
            self.assets_investments_bar_chart_view.setChart(_empty_chart())
            self.assets_investments_bar_chart_view.setVisible(False)
            self.assets_investments_pies_panel.setVisible(False)
            self.range_label.setText("")
            self.view_selector_row.setVisible(False)
            self.investment_controls_row.setVisible(False)
            self.projection_controls_scroll_area.setVisible(False)
            self.college_tuition_controls_scroll_area.setVisible(False)
            return
        report_id = self.list_model.id_at(indexes[0].row())
        self._active_report_id = report_id
        is_category_report = report_id in self._category_reports
        is_investment_report = report_id == INVESTMENT_ANALYSIS_REPORT_ID
        is_projection_report = report_id == NET_WORTH_PROJECTION_REPORT_ID
        is_college_tuition_report = report_id == COLLEGE_TUITION_PROJECTION_REPORT_ID
        is_assets_investments_report = report_id == ASSETS_AND_INVESTMENTS_REPORT_ID
        is_recurring_report = report_id == RECURRING_SUBSCRIPTIONS_REPORT_ID
        is_rsu_vesting_report = report_id == RSU_VESTING_FORECAST_REPORT_ID
        self.view_selector_row.setVisible(
            is_category_report or is_assets_investments_report or is_rsu_vesting_report
        )
        self.custom_categories_button.setVisible(is_category_report)
        if is_category_report:
            self.view_selector.blockSignals(True)
            self.view_selector.clear()
            self.view_selector.addItems(["Table", "Pie Chart"])
            self.view_selector.setCurrentIndex(0)
            self.view_selector.blockSignals(False)
            self.category_table_view.setModel(self._category_reports[report_id]["model"])
        elif is_assets_investments_report:
            self.view_selector.blockSignals(True)
            self.view_selector.clear()
            self.view_selector.addItems(["Table", "Bar Chart", "Pie Charts"])
            self.view_selector.setCurrentIndex(0)
            self.view_selector.blockSignals(False)
        elif is_rsu_vesting_report:
            self.view_selector.blockSignals(True)
            self.view_selector.clear()
            self.view_selector.addItems(["Table", "Chart"])
            self.view_selector.setCurrentIndex(0)
            self.view_selector.blockSignals(False)
        self.chart_view.setVisible(
            report_id
            in (NET_WORTH_REPORT_ID, NET_WORTH_PROJECTION_REPORT_ID, COLLEGE_TUITION_PROJECTION_REPORT_ID)
        )
        self.category_table_view.setVisible(is_category_report)
        self.investment_table_view.setVisible(is_investment_report)
        self.investment_controls_row.setVisible(is_investment_report)
        self.projection_controls_scroll_area.setVisible(is_projection_report)
        self.college_tuition_controls_scroll_area.setVisible(is_college_tuition_report)
        self.assets_investments_table_view.setVisible(is_assets_investments_report)
        self.recurring_table_view.setVisible(is_recurring_report)
        self.rsu_vesting_forecast_table_view.setVisible(is_rsu_vesting_report)
        self.rsu_vesting_controls_row.setVisible(is_rsu_vesting_report)
        self.rsu_vesting_charts_panel.setVisible(False)
        self.assets_investments_bar_chart_view.setVisible(False)
        self.assets_investments_pies_panel.setVisible(False)
        self.range_controls_row.setVisible(
            not is_projection_report
            and not is_college_tuition_report
            and not is_assets_investments_report
            and not is_rsu_vesting_report
        )
        self.range_label.setVisible(
            not is_projection_report
            and not is_college_tuition_report
            and not is_assets_investments_report
            and not is_rsu_vesting_report
        )
        if report_id == NET_WORTH_REPORT_ID:
            self._load_net_worth_report()
        elif is_category_report:
            self._load_category_report(report_id)
        elif is_investment_report:
            self._load_investment_report()
        elif is_projection_report:
            self._load_projection_report()
        elif is_college_tuition_report:
            self._load_college_tuition_report()
        elif is_assets_investments_report:
            self._load_assets_and_investments_report()
        elif is_recurring_report:
            self._load_recurring_report()
        elif is_rsu_vesting_report:
            self._load_rsu_vesting_forecast_report()

    def _on_view_mode_changed(self):
        if self._active_report_id in self._category_reports:
            is_pie_chart = self.view_selector.currentText() == "Pie Chart"
            self.chart_view.setVisible(is_pie_chart)
            self.category_table_view.setVisible(not is_pie_chart)
            if is_pie_chart:
                self._render_pie_chart()
        elif self._active_report_id == ASSETS_AND_INVESTMENTS_REPORT_ID:
            mode = self.view_selector.currentText()
            self.assets_investments_table_view.setVisible(mode == "Table")
            self.assets_investments_bar_chart_view.setVisible(mode == "Bar Chart")
            self.assets_investments_pies_panel.setVisible(mode == "Pie Charts")
            if mode == "Bar Chart":
                self._render_assets_investments_bar_chart()
            elif mode == "Pie Charts":
                self._render_assets_investments_pie_charts()
        elif self._active_report_id == RSU_VESTING_FORECAST_REPORT_ID:
            is_chart = self.view_selector.currentText() == "Chart"
            self.rsu_vesting_forecast_table_view.setVisible(not is_chart)
            self.rsu_vesting_charts_panel.setVisible(is_chart)
            if is_chart:
                self._render_rsu_vesting_charts()

    def _load_net_worth_report(self):
        # Show the spinner before doing any work: fetching every account's
        # transactions below is synchronous and can be slow, so it must not
        # run until Qt has had a chance to paint the busy indicator -- hence
        # deferring the actual loading to the next event-loop tick.
        self.net_worth_status_row.setVisible(True)
        self.net_worth_busy_indicator.start()
        QTimer.singleShot(0, self._load_net_worth_report_accounts)

    def _load_net_worth_report_accounts(self):
        try:
            accounts = data.list_accounts(self._conn, include_closed=True)
        except Exception as exc:
            self.net_worth_busy_indicator.stop()
            self.net_worth_status_row.setVisible(False)
            self._report_error(f"Failed to load net worth report: {exc}")
            return

        account_inputs = []
        for account_id, _name, account_type, currency, _balance, is_closed, _is_favorite in accounts:
            is_investment = account_type == INVESTMENT_ACCOUNT_TYPE
            opening_balance = data.get_opening_balance(self._conn, account_id)
            date_opened = data.get_date_opened(self._conn, account_id)
            try:
                transactions = data.list_transactions(self._conn, account_id)
            except Exception as exc:
                self.net_worth_busy_indicator.stop()
                self.net_worth_status_row.setVisible(False)
                self._report_error(f"Failed to load net worth report: {exc}")
                return
            account_inputs.append((currency, opening_balance, is_investment, transactions, date_opened, is_closed))

        def _compute():
            account_series = []
            earliest = latest = None
            for currency, opening_balance, is_investment, transactions, date_opened, is_closed in account_inputs:
                history = compute_account_value_history(transactions, opening_balance, is_investment)
                initial_value = Decimal("0") if is_investment else (opening_balance or Decimal("0"))
                account_series.append((currency, initial_value, history, date_opened, is_closed))
                if history:
                    earliest = history[0][0] if earliest is None else min(earliest, history[0][0])
                    latest = history[-1][0] if latest is None else max(latest, history[-1][0])
            return account_series, earliest, latest

        def _on_success(result):
            account_series, earliest, latest = result
            if earliest is None:
                self.net_worth_status_row.setVisible(False)
                self._net_worth_accounts = []
                self.chart_view.setChart(_empty_chart())
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

        def _on_error(message):
            self.net_worth_status_row.setVisible(False)
            self._report_error(f"Failed to load net worth report: {message}")

        self.net_worth_status_row.setVisible(True)
        self._net_worth_worker = run_in_background(
            _compute, self.net_worth_busy_indicator, on_success=_on_success, on_error=_on_error, parent=self
        )

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
        elif self._active_report_id == INVESTMENT_ANALYSIS_REPORT_ID:
            start = self.start_date_edit.date().toPython()
            end = self.end_date_edit.date().toPython()
            if start > end:
                self._report_error("Start date must be on or before end date.")
                return
            self._render_investment_table(start, end)
        elif self._active_report_id == RECURRING_SUBSCRIPTIONS_REPORT_ID:
            start = self.start_date_edit.date().toPython()
            end = self.end_date_edit.date().toPython()
            if start > end:
                self._report_error("Start date must be on or before end date.")
                return
            self._render_recurring_table(start, end)

    def _render_net_worth_chart(self, start, end):
        accounts = self._net_worth_accounts
        to_usd = self._to_usd

        def _compute():
            sample_dates = generate_sample_dates(start, end, months=2)
            series = compute_net_worth_series(accounts, sample_dates, to_usd)
            categories = [sample_date.isoformat() for sample_date, _ in series]
            values = [total for _, total in series]
            return categories, values

        def _on_success(result):
            categories, values = result
            chart = build_bar_chart("Net Worth Over Time (USD)", categories, values)
            self.chart_view.setChart(chart)
            self.range_label.setText(f"Showing {start.isoformat()} to {end.isoformat()}")
            self.net_worth_status_row.setVisible(False)

        def _on_error(message):
            self.net_worth_status_row.setVisible(False)
            self._report_error(f"Failed to render net worth report: {message}")

        self.net_worth_status_row.setVisible(True)
        self._net_worth_worker = run_in_background(
            _compute, self.net_worth_busy_indicator, on_success=_on_success, on_error=_on_error, parent=self
        )

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

    def _load_investment_report(self):
        self._selected_investments = None
        try:
            prices = data.list_investment_prices(self._conn)
        except Exception as exc:
            self._report_error(f"Failed to load investment analysis report: {exc}")
            return

        if not prices:
            self._investment_prices = []
            self.investment_table_model.set_investments([])
            self.range_label.setText("")
            self._report_error("No priced investment trades available for investment analysis report.")
            return

        self._investment_prices = prices
        earliest = min(txn_date for _, txn_date, _ in prices)
        latest = max(txn_date for _, txn_date, _ in prices)

        self.start_date_edit.blockSignals(True)
        self.end_date_edit.blockSignals(True)
        self.start_date_edit.setDate(_to_qdate(earliest))
        self.end_date_edit.setDate(_to_qdate(latest))
        self.start_date_edit.blockSignals(False)
        self.end_date_edit.blockSignals(False)

        self._render_investment_table(earliest, latest)

    def _load_rsu_vesting_forecast_report(self):
        try:
            self._rsu_vests = data.list_upcoming_vests(self._conn)
        except Exception as exc:
            self._report_error(f"Failed to load RSU vesting forecast report: {exc}")
            return
        settings = load_rsu_tax_settings()
        self.rsu_vesting_tax_rate_spinbox.blockSignals(True)
        self.rsu_vesting_tax_rate_spinbox.setValue(settings.get("tax_rate", RSU_DEFAULT_TAX_RATE))
        self.rsu_vesting_tax_rate_spinbox.blockSignals(False)
        self._render_rsu_vesting_table()

    def _on_rsu_vesting_tax_rate_changed(self):
        save_rsu_tax_settings({"tax_rate": self.rsu_vesting_tax_rate_spinbox.value()})
        self._render_rsu_vesting_table()
        if self.rsu_vesting_charts_panel.isVisible():
            self._render_rsu_vesting_charts()

    def _rsu_vesting_tax_rate(self):
        return Decimal(str(self.rsu_vesting_tax_rate_spinbox.value())) / Decimal("100")

    def _render_rsu_vesting_table(self):
        rows = compute_rsu_vesting_forecast(self._rsu_vests, self._to_usd, self._rsu_vesting_tax_rate())
        self.rsu_vesting_forecast_table_model.set_rows(rows)

    def _render_rsu_vesting_charts(self):
        shares_series, shares_taxed_series, value_series, tax_series = compute_rsu_vesting_cumulative_series(
            self._rsu_vests, self._to_usd, self._rsu_vesting_tax_rate()
        )
        self.rsu_vesting_shares_chart_view.setChart(
            build_line_chart(
                "Cumulative Shares Vesting",
                [("Shares Vesting", shares_series), ("Shares Taxed", shares_taxed_series)],
            )
        )
        self.rsu_vesting_value_chart_view.setChart(
            build_line_chart(
                "Cumulative Vesting Value (USD)",
                [("Value Vesting", value_series), ("Tax Owed", tax_series)],
            )
        )

    def _render_investment_table(self, start, end):
        investments = compute_investment_analysis(self._investment_prices, start, end)
        if self._selected_investments is not None:
            investments = [row for row in investments if row[0] in self._selected_investments]
        self.investment_table_model.set_investments(investments)
        self.range_label.setText(f"Showing {start.isoformat()} to {end.isoformat()}")

    def _load_recurring_report(self):
        # Show the spinner before the (synchronous, potentially slow) fetch
        # below runs, deferred to the next event-loop tick so Qt paints it first.
        self.recurring_status_row.setVisible(True)
        self.recurring_busy_indicator.start()
        QTimer.singleShot(0, self._load_recurring_report_transactions)

    def _load_recurring_report_transactions(self):
        try:
            transactions = data.list_recurring_candidate_transactions(self._conn)
        except Exception as exc:
            self.recurring_busy_indicator.stop()
            self.recurring_status_row.setVisible(False)
            self._report_error(f"Failed to load recurring/subscriptions report: {exc}")
            return

        if not transactions:
            self.recurring_busy_indicator.stop()
            self.recurring_status_row.setVisible(False)
            self._recurring_transactions = []
            self.recurring_table_model.set_recurring([])
            self.range_label.setText("")
            self._report_error("No payee-attributed spending available for recurring/subscriptions report.")
            return

        self._recurring_transactions = transactions
        earliest = min(txn_date for _, _, _, txn_date, _, _ in transactions)
        latest = max(txn_date for _, _, _, txn_date, _, _ in transactions)
        default_start = max(earliest, add_months(_today(), -RECURRING_DEFAULT_LOOKBACK_MONTHS))

        self.start_date_edit.blockSignals(True)
        self.end_date_edit.blockSignals(True)
        self.start_date_edit.setDate(_to_qdate(default_start))
        self.end_date_edit.setDate(_to_qdate(latest))
        self.start_date_edit.blockSignals(False)
        self.end_date_edit.blockSignals(False)

        self._render_recurring_table(default_start, latest)

    def _render_recurring_table(self, start, end):
        self.recurring_status_row.setVisible(True)
        self.update_range_button.setEnabled(False)
        transactions = self._recurring_transactions
        to_usd = self._to_usd

        def _on_success(recurring):
            self.recurring_table_model.set_recurring(recurring)
            self.range_label.setText(f"Showing {start.isoformat()} to {end.isoformat()}")
            self.recurring_status_row.setVisible(False)
            self.update_range_button.setEnabled(True)

        def _on_error(message):
            self.recurring_status_row.setVisible(False)
            self.update_range_button.setEnabled(True)
            self._report_error(f"Failed to compute recurring/subscriptions report: {message}")

        # Keep a reference on self -- PySide destroys a QThread whose last
        # Python reference disappears while it's still running.
        self._recurring_worker = run_in_background(
            lambda: compute_recurring_transactions(transactions, start, end, to_usd),
            self.recurring_busy_indicator,
            on_success=_on_success,
            on_error=_on_error,
            parent=self,
        )

    def _load_projection_report(self):
        try:
            accounts = data.list_accounts(self._conn, include_closed=False)
        except Exception as exc:
            self._report_error(f"Failed to load net worth projection report: {exc}")
            return

        starting_value = sum(
            (
                self._to_usd(currency, balance)
                for _account_id, _name, account_type, currency, balance, _is_closed, _is_favorite
                in accounts
                if account_type == INVESTMENT_ACCOUNT_TYPE
            ),
            start=Decimal("0"),
        )

        asset_accounts = [
            (account_id, name)
            for account_id, name, account_type, _currency, _balance, _is_closed, _is_favorite
            in accounts
            if account_type == ASSET_ACCOUNT_TYPE
        ]
        self._projection_asset_values = {
            account_id: self._to_usd(currency, balance)
            for account_id, name, account_type, currency, balance, _is_closed, _is_favorite
            in accounts
            if account_type == ASSET_ACCOUNT_TYPE
        }
        self.projection_controls.set_house_accounts(asset_accounts)

        values = default_projection_values()
        values.update(load_projection_settings())
        values["starting_investment_value"] = float(starting_value)
        self.projection_controls.set_values(values)
        self._render_projection_chart()

    def _on_projection_updated(self):
        values = self.projection_controls.values()
        save_projection_settings(
            {key: value for key, value in values.items() if key != "starting_investment_value"}
        )
        self._render_projection_chart()

    def _render_projection_chart(self):
        values = self.projection_controls.values()
        hundred = Decimal("100")
        house_sale_value = self._projection_asset_values.get(
            values["house_account_id"], Decimal("0")
        )
        inputs = ProjectionInputs(
            birth_year=values["birth_year"],
            end_year=values["end_year"],
            retirement_age=values["retirement_age"],
            starting_investment_value=Decimal(str(values["starting_investment_value"])),
            return_rate_before_retirement=Decimal(str(values["return_rate_before_retirement"])) / hundred,
            return_rate_after_retirement=Decimal(str(values["return_rate_after_retirement"])) / hundred,
            annual_income=Decimal(str(values["annual_income"])),
            tax_rate=Decimal(str(values["tax_rate"])) / hundred,
            inflation_rate=Decimal(str(values["inflation_rate"])) / hundred,
            spending_before_retirement=Decimal(str(values["spending_before_retirement"])),
            spending_after_retirement=Decimal(str(values["spending_after_retirement"])),
            social_security_annual_amount=Decimal(str(values["social_security_annual_amount"])),
            social_security_start_year=values["social_security_start_year"],
            social_security_annual_amount_2=Decimal(str(values["social_security_annual_amount_2"])),
            social_security_start_year_2=values["social_security_start_year_2"],
            house_sale_value=house_sale_value,
            house_sale_year=values["house_sale_year"],
            inheritance_amount=Decimal(str(values["inheritance_amount"])),
            inheritance_year=values["inheritance_year"],
            medical_cost_after_retirement=Decimal(str(values["medical_cost_after_retirement"])),
            medicare_age=values["medicare_age"],
            withdrawal_tax_rate=Decimal(str(values["withdrawal_tax_rate"])) / hundred,
        )
        rows = compute_projection(inputs)
        assets_total = sum(self._projection_asset_values.values(), start=Decimal("0"))
        assets_total_after_house_sale = assets_total - house_sale_value
        house_sale_year = values["house_sale_year"]
        bands = [
            (
                "Assets",
                [
                    (
                        date(row.year, 1, 1),
                        assets_total_after_house_sale if row.year >= house_sale_year else assets_total,
                    )
                    for row in rows
                ],
                "#ADD8E6",
            ),
            ("Investments", [(date(row.year, 1, 1), row.net_worth) for row in rows], "#FFCC80"),
        ]
        chart = build_stacked_area_chart("Net Worth Projection (USD)", bands, mark_zero=True)
        self.chart_view.setChart(chart)

    def _load_college_tuition_report(self):
        try:
            accounts = data.list_accounts(self._conn, include_closed=False)
        except Exception as exc:
            self._report_error(f"Failed to load college tuition projection report: {exc}")
            return

        investment_accounts = [
            (account_id, name)
            for account_id, name, account_type, _currency, _balance, _is_closed, _is_favorite
            in accounts
            if account_type == INVESTMENT_ACCOUNT_TYPE
        ]
        balances = {
            account_id: self._to_usd(currency, balance)
            for account_id, _name, account_type, currency, balance, _is_closed, _is_favorite
            in accounts
            if account_type == INVESTMENT_ACCOUNT_TYPE
        }
        self.college_tuition_controls.set_accounts(investment_accounts, balances)

        values = default_college_tuition_values()
        values.update(load_college_tuition_settings())
        self.college_tuition_controls.set_values(values)
        self._render_college_tuition_chart()

    def _on_college_tuition_updated(self):
        values = self.college_tuition_controls.values()
        save_college_tuition_settings(
            {key: value for key, value in values.items() if key != "starting_fund_value"}
        )
        self._render_college_tuition_chart()

    def _render_college_tuition_chart(self):
        values = self.college_tuition_controls.values()
        hundred = Decimal("100")
        inputs = CollegeTuitionInputs(
            starting_fund_value=Decimal(str(values["starting_fund_value"])),
            annual_return_rate=Decimal(str(values["annual_return_rate"])) / hundred,
            contribution_per_quarter=Decimal(str(values["contribution_per_quarter"])),
            contribution_end_year=values["contribution_end_year"],
            person1=PersonCollegeCosts(
                start_year=values["person1_start_year"],
                end_year=values["person1_end_year"],
                tuition_per_quarter=Decimal(str(values["person1_tuition_per_quarter"])),
                housing_per_quarter=Decimal(str(values["person1_housing_per_quarter"])),
            ),
            person2=PersonCollegeCosts(
                start_year=values["person2_start_year"],
                end_year=values["person2_end_year"],
                tuition_per_quarter=Decimal(str(values["person2_tuition_per_quarter"])),
                housing_per_quarter=Decimal(str(values["person2_housing_per_quarter"])),
            ),
        )
        rows = compute_college_tuition_projection(inputs)
        quarter_start_month = {1: 1, 2: 4, 3: 7, 4: 10}
        series = [
            (
                "College Fund Balance",
                [(date(row.year, quarter_start_month[row.quarter], 1), row.fund_value) for row in rows],
            )
        ]
        chart = build_line_chart("College Tuition Projection (USD)", series, mark_zero=True)
        self.chart_view.setChart(chart)

    def _load_assets_and_investments_report(self):
        try:
            accounts = data.list_accounts(self._conn, include_closed=False)
        except Exception as exc:
            self._report_error(f"Failed to load assets and investments report: {exc}")
            return
        rows = compute_assets_and_investments(accounts, self._to_usd)
        self.assets_investments_table_model.set_rows(rows)
        self._assets_investments_breakdown = compute_assets_and_investments_breakdown(accounts, self._to_usd)

    def _render_assets_investments_bar_chart(self):
        chart = build_grouped_stacked_bar_chart(
            "Assets and Investments (USD)", self._assets_investments_breakdown
        )
        self.assets_investments_bar_chart_view.setChart(chart)

    def _render_assets_investments_pie_charts(self):
        for section_label, accounts in self._assets_investments_breakdown:
            chart = build_pie_chart(section_label, accounts)
            self.assets_investments_pie_charts[section_label].setChart(chart)

    def _on_custom_investments_clicked(self):
        all_names = sorted({name for name, _txn_date, _price in self._investment_prices})
        current_selection = (
            self._selected_investments if self._selected_investments is not None else set(all_names)
        )
        dialog = InvestmentFilterDialog(all_names, current_selection, self)
        if dialog.exec() != QDialog.Accepted:
            return
        self._selected_investments = dialog.selected_investments()
        start = self.start_date_edit.date().toPython()
        end = self.end_date_edit.date().toPython()
        self._render_investment_table(start, end)

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
