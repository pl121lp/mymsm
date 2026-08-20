"""Main window: account list (left) + transaction table (right)."""

from decimal import Decimal

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

import data
from data import INVESTMENT_ACCOUNT_TYPE
from models import AccountTableModel, TransactionTableModel, account_type_label, format_currency

SETTINGS_ORG = "mymsm"
SETTINGS_APP = "MoneyBrowser"
SETTINGS_KEY_SEK_RATE = "sek_to_usd_rate"
DEFAULT_SEK_TO_USD_RATE = 0.095


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
        self.account_view.horizontalHeader().setStretchLastSection(True)
        self.account_view.resizeColumnsToContents()
        self.account_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.account_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.account_view.selectionModel().selectionChanged.connect(self._on_account_selected)

        self.account_details_label = QLabel()

        self.transaction_view = QTableView()
        self.transaction_view.setModel(self.transaction_model)
        self.transaction_view.horizontalHeader().setStretchLastSection(True)
        self.transaction_view.setSortingEnabled(True)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.total_label)
        left_layout.addLayout(rate_row)
        left_layout.addWidget(self.show_closed_checkbox)
        left_layout.addWidget(self.account_view)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.addWidget(self.account_details_label)
        right_layout.addWidget(self.transaction_view)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        self.setCentralWidget(splitter)

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
        self._update_total_label()
        self.account_details_label.setText("")
        self.transaction_model.set_transactions([])

    def _on_account_selected(self, selected=None, deselected=None):
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
