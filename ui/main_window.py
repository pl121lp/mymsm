"""Main window: account list (left) + transaction/details panel (right)."""

from decimal import Decimal
from functools import partial

from PySide6.QtCharts import QChartView
from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDoubleSpinBox,
    QFormLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

import data
from add_record_dialog import AddRecordDialog
from charts import build_line_chart
from data import INVESTMENT_ACCOUNT_TYPE
from dictionaries_tab import CategoriesPane, InvestmentsPane, PayeesPane
from models import (
    AccountTableModel,
    TransactionTableModel,
    account_type_label,
    compute_account_value_history,
    format_currency,
)
from table_copy import enable_cell_copy, enable_label_copy

SETTINGS_ORG = "mymsm"
SETTINGS_APP = "MoneyBrowser"
SETTINGS_KEY_SEK_RATE = "sek_to_usd_rate"
DEFAULT_SEK_TO_USD_RATE = 0.095

TRANSACTIONS_PAGE = 0
DETAILS_PAGE = 1
VALUE_PAGE = 2

ROW_BUTTON_STYLE = "padding: 1px 6px;"


class MainWindow(QMainWindow):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self.setWindowTitle("Money Browser")
        self.resize(1000, 600)

        self.account_model = AccountTableModel()
        self.transaction_model = TransactionTableModel()

        self.total_label = QLabel()
        enable_label_copy(self.total_label)

        self.sek_rate_spinbox = QDoubleSpinBox()
        self.sek_rate_spinbox.setRange(0.0001, 1000.0)
        self.sek_rate_spinbox.setDecimals(4)
        self.sek_rate_spinbox.setSingleStep(0.001)
        self.sek_rate_spinbox.setValue(
            self._settings.value(SETTINGS_KEY_SEK_RATE, DEFAULT_SEK_TO_USD_RATE, type=float)
        )
        self.sek_rate_spinbox.valueChanged.connect(self._on_exchange_rate_changed)
        self._apply_exchange_rate()

        rate_row = QHBoxLayout()
        rate_row.addWidget(QLabel("1 SEK ="))
        rate_row.addWidget(self.sek_rate_spinbox)
        rate_row.addWidget(QLabel("USD"))
        rate_row.addStretch()

        self.show_closed_checkbox = QCheckBox("Show closed accounts")
        self.show_closed_checkbox.stateChanged.connect(self._reload_accounts)

        self.account_view = QTableView()
        self.account_view.setModel(self.account_model)
        self.account_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.account_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.account_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.account_view.selectionModel().selectionChanged.connect(self._on_account_selected)
        enable_cell_copy(self.account_view)

        self.account_details_label = QLabel()
        enable_label_copy(self.account_details_label)

        self.transaction_view = QTableView()
        self.transaction_view.setModel(self.transaction_model)
        self.transaction_view.horizontalHeader().setStretchLastSection(True)
        self.transaction_view.setSortingEnabled(True)
        self.transaction_view.doubleClicked.connect(self._on_transaction_double_clicked)
        enable_cell_copy(self.transaction_view, on_edit=self._edit_transaction)

        transactions_page = QWidget()
        transactions_layout = QVBoxLayout(transactions_page)
        transactions_layout.addWidget(self.account_details_label)
        transactions_layout.addWidget(self.transaction_view)

        self.details_name_value = QLabel()
        self.details_type_value = QLabel()
        self.details_currency_value = QLabel()
        self.details_opening_balance_value = QLabel()
        self.details_balance_value = QLabel()
        self.details_status_value = QLabel()
        for value_label in (
            self.details_name_value,
            self.details_type_value,
            self.details_currency_value,
            self.details_opening_balance_value,
            self.details_balance_value,
            self.details_status_value,
        ):
            enable_label_copy(value_label)

        details_page = QWidget()
        details_form = QFormLayout(details_page)
        details_form.addRow("Name:", self.details_name_value)
        details_form.addRow("Type:", self.details_type_value)
        details_form.addRow("Currency:", self.details_currency_value)
        details_form.addRow("Starting balance:", self.details_opening_balance_value)
        self.details_balance_label = QLabel("Balance:")
        details_form.addRow(self.details_balance_label, self.details_balance_value)
        details_form.addRow("Status:", self.details_status_value)
        details_form.setAlignment(Qt.AlignTop)

        self.value_chart_view = QChartView()
        self.value_chart_view.setRenderHint(QPainter.Antialiasing)

        value_page = QWidget()
        value_layout = QVBoxLayout(value_page)
        value_layout.addWidget(self.value_chart_view)

        self.right_stack = QStackedWidget()
        self.right_stack.addWidget(transactions_page)
        self.right_stack.addWidget(details_page)
        self.right_stack.addWidget(value_page)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.total_label)
        left_layout.addLayout(rate_row)
        left_layout.addWidget(self.show_closed_checkbox)
        left_layout.addWidget(self.account_view)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self.right_stack)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        self.categories_pane = CategoriesPane(self._conn, self.statusBar().showMessage)
        self.payees_pane = PayeesPane(self._conn, self.statusBar().showMessage)
        self.investments_pane = InvestmentsPane(self._conn, self.statusBar().showMessage)

        dictionaries_tabs = QTabWidget()
        dictionaries_tabs.addTab(self.categories_pane, "Categories")
        dictionaries_tabs.addTab(self.payees_pane, "Payees")
        dictionaries_tabs.addTab(self.investments_pane, "Investments")

        tabs = QTabWidget()
        tabs.addTab(splitter, "Accounts")
        tabs.addTab(dictionaries_tabs, "Dictionaries")
        self.setCentralWidget(tabs)

        self._reload_accounts()

    def _apply_exchange_rate(self):
        rate = Decimal(str(self.sek_rate_spinbox.value()))
        self.account_model.set_exchange_rates({"SEK": rate})

    def _update_total_label(self):
        self.total_label.setText(f"Total: {format_currency(self.account_model.total_usd())} USD")

    def _on_exchange_rate_changed(self, value):
        self._settings.setValue(SETTINGS_KEY_SEK_RATE, value)
        self._apply_exchange_rate()
        self._update_total_label()

    def _reload_accounts(self):
        include_closed = self.show_closed_checkbox.isChecked()
        try:
            accounts = data.list_accounts(self._conn, include_closed=include_closed)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to load accounts: {exc}")
            return
        self.account_model.set_accounts(accounts)
        self.account_view.resizeColumnsToContents()
        self._install_row_action_buttons()
        self._update_total_label()
        self.account_details_label.setText("")
        self.transaction_model.set_transactions([])
        self.right_stack.setCurrentIndex(TRANSACTIONS_PAGE)

    def _install_row_action_buttons(self):
        actions_col = self.account_model.COLUMNS.index("Actions")
        column_width = 0
        for row in range(self.account_model.rowCount()):
            container = QWidget()
            layout = QHBoxLayout(container)
            layout.setContentsMargins(2, 0, 2, 0)
            layout.setSpacing(4)

            details_button = QPushButton("Details")
            details_button.setStyleSheet(ROW_BUTTON_STYLE)
            details_button.clicked.connect(partial(self._on_details_button_clicked, row))
            layout.addWidget(details_button)

            transactions_button = QPushButton("Transactions")
            transactions_button.setStyleSheet(ROW_BUTTON_STYLE)
            transactions_button.clicked.connect(partial(self._on_transactions_button_clicked, row))
            layout.addWidget(transactions_button)

            value_button = QPushButton("Value")
            value_button.setStyleSheet(ROW_BUTTON_STYLE)
            value_button.clicked.connect(partial(self._on_value_button_clicked, row))
            layout.addWidget(value_button)

            add_record_button = QPushButton("Add Record")
            add_record_button.setStyleSheet(ROW_BUTTON_STYLE)
            add_record_button.clicked.connect(partial(self._on_add_record_button_clicked, row))
            layout.addWidget(add_record_button)

            self.account_view.setIndexWidget(self.account_model.index(row, actions_col), container)
            column_width = max(column_width, container.sizeHint().width())
        if column_width:
            self.account_view.horizontalHeader().resizeSection(actions_col, column_width)

    def _on_transactions_button_clicked(self, row):
        self.account_view.selectRow(row)
        self._on_account_selected()

    def _on_details_button_clicked(self, row):
        account_id, name, account_type, currency, balance, is_closed = self.account_model.account_at(
            row
        )
        opening_balance = data.get_opening_balance(self._conn, account_id)
        is_investment = account_type == INVESTMENT_ACCOUNT_TYPE

        self.details_name_value.setText(f"(CLOSED) {name}" if is_closed else name)
        self.details_type_value.setText(account_type_label(account_type))
        self.details_currency_value.setText(currency)
        self.details_opening_balance_value.setText(
            f"{format_currency(opening_balance)} {currency}" if opening_balance is not None else ""
        )
        self.details_balance_label.setText("Value:" if is_investment else "Balance:")
        usd_balance = self.account_model.to_usd(currency, balance)
        self.details_balance_value.setText(f"{format_currency(usd_balance)} USD")
        self.details_status_value.setText("Closed" if is_closed else "Open")

        self.right_stack.setCurrentIndex(DETAILS_PAGE)

    def _on_value_button_clicked(self, row):
        account_id, name, account_type, currency, _, _ = self.account_model.account_at(row)
        is_investment = account_type == INVESTMENT_ACCOUNT_TYPE
        opening_balance = data.get_opening_balance(self._conn, account_id)
        try:
            transactions = data.list_transactions(self._conn, account_id)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to load account history: {exc}")
            return

        history = compute_account_value_history(transactions, opening_balance, is_investment)
        usd_history = [
            (txn_date, self.account_model.to_usd(currency, value)) for txn_date, value in history
        ]
        chart = build_line_chart(f"{name} — Value (USD)", [(name, usd_history)])
        self.value_chart_view.setChart(chart)
        self.right_stack.setCurrentIndex(VALUE_PAGE)

    def _on_add_record_button_clicked(self, row):
        account_id, _name, account_type, _currency, _balance, _is_closed = self.account_model.account_at(
            row
        )
        dialog = AddRecordDialog(self._conn, account_id, account_type, parent=self)
        if dialog.exec() != AddRecordDialog.Accepted:
            return
        self._reload_accounts()
        self.categories_pane._reload()
        self.payees_pane._reload()
        self.investments_pane._reload()
        self.account_view.selectRow(row)
        self._on_account_selected()
        self.statusBar().showMessage("Record added.")

    def _on_transaction_double_clicked(self, index):
        self._edit_transaction(index.row())

    def _edit_transaction(self, row):
        indexes = self.account_view.selectionModel().selectedRows()
        if not indexes:
            return
        account_row = indexes[0].row()
        account_id, _name, account_type, _currency, _balance, _is_closed = self.account_model.account_at(
            account_row
        )
        transaction = self.transaction_model.transaction_at(row)
        dialog = AddRecordDialog(self._conn, account_id, account_type, transaction=transaction, parent=self)
        if dialog.exec() != AddRecordDialog.Accepted:
            return
        self._reload_accounts()
        self.categories_pane._reload()
        self.payees_pane._reload()
        self.investments_pane._reload()
        self.account_view.selectRow(account_row)
        self._on_account_selected()
        self.statusBar().showMessage("Record updated.")

    def _on_account_selected(self, selected=None, deselected=None):
        self.right_stack.setCurrentIndex(TRANSACTIONS_PAGE)
        indexes = self.account_view.selectionModel().selectedRows()
        if not indexes:
            self.account_details_label.setText("")
            self.transaction_model.set_transactions([])
            return
        account_id, name, account_type, currency, balance, _ = self.account_model.account_at(
            indexes[0].row()
        )
        is_investment = account_type == INVESTMENT_ACCOUNT_TYPE
        balance_label = "Value" if is_investment else "Balance"
        usd_balance = self.account_model.to_usd(currency, balance)
        self.account_details_label.setText(
            f"{name} ({account_type_label(account_type)}) — "
            f"{balance_label}: {format_currency(usd_balance)} USD"
        )
        try:
            transactions = data.list_transactions(self._conn, account_id)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to load transactions: {exc}")
            return
        self.transaction_model.set_transactions(transactions, is_investment=is_investment)
        self.transaction_view.resizeColumnsToContents()
