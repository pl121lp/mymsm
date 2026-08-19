"""Main window: account list (left) + transaction table (right)."""

from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QHBoxLayout,
    QMainWindow,
    QTableView,
    QVBoxLayout,
    QWidget,
)

import data
from models import AccountTableModel, TransactionTableModel


class MainWindow(QMainWindow):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.setWindowTitle("Money Browser")
        self.resize(1000, 600)

        self.account_model = AccountTableModel()
        self.transaction_model = TransactionTableModel()

        self.show_closed_checkbox = QCheckBox("Show closed accounts")
        self.show_closed_checkbox.stateChanged.connect(self._reload_accounts)

        self.account_view = QTableView()
        self.account_view.setModel(self.account_model)
        self.account_view.horizontalHeader().setStretchLastSection(True)
        self.account_view.resizeColumnsToContents()
        self.account_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.account_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.account_view.selectionModel().selectionChanged.connect(self._on_account_selected)

        self.transaction_view = QTableView()
        self.transaction_view.setModel(self.transaction_model)
        self.transaction_view.horizontalHeader().setStretchLastSection(True)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.show_closed_checkbox)
        left_layout.addWidget(self.account_view)

        central = QWidget()
        layout = QHBoxLayout(central)
        layout.addWidget(left, 1)
        layout.addWidget(self.transaction_view, 2)
        self.setCentralWidget(central)

        self._reload_accounts()

    def _reload_accounts(self):
        include_closed = self.show_closed_checkbox.isChecked()
        try:
            accounts = data.list_accounts(self._conn, include_closed=include_closed)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to load accounts: {exc}")
            return
        self.account_model.set_accounts(accounts)
        self.account_view.resizeColumnsToContents()
        self.transaction_model.set_transactions([])

    def _on_account_selected(self, selected=None, deselected=None):
        indexes = self.account_view.selectionModel().selectedRows()
        if not indexes:
            self.transaction_model.set_transactions([])
            return
        account_id = self.account_model.account_id_at(indexes[0].row())
        try:
            transactions = data.list_transactions(self._conn, account_id)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to load transactions: {exc}")
            return
        self.transaction_model.set_transactions(transactions)
        self.transaction_view.resizeColumnsToContents()
