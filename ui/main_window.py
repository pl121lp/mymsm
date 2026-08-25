"""Main window: account list (left) + transaction/details panel (right)."""

from datetime import date
from decimal import Decimal
from functools import partial

from PySide6.QtCharts import QChartView
from PySide6.QtCore import QEvent, QSettings, Qt, QUrl
from PySide6.QtGui import QKeySequence, QPainter, QShortcut
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTableView,
    QVBoxLayout,
    QWidget,
)

import data
import writes
from account_details_dialog import AccountDetailsDialog
from add_account_dialog import AddAccountDialog
from add_record_dialog import AddRecordDialog
from amortization import AmortizationInputs, compute_future_amortization, infer_payments_per_year
from charts import build_line_chart
from data import INVESTMENT_ACCOUNT_TYPE, LOAN_ACCOUNT_TYPE
from dictionaries_tab import CategoriesPane, InvestmentsPane, PayeesPane
from exchange_rate import FRANKFURTER_URL, parse_rate_response
from import_qfx_dialog import ImportQfxDialog
from models import (
    AccountTableModel,
    TransactionTableModel,
    account_type_label,
    build_loan_transaction_rows,
    compute_account_value_history,
    compute_loan_totals,
    format_currency,
)
from navigation_history import NavigationHistory
from qfx_import import parse_qfx
from reports_tab import ReportsPane
from search_tab import SearchPane
from table_copy import enable_cell_copy, enable_label_copy
from undo import AddCommand, DeleteCommand, EditCommand, ImportCommand, UndoStack

SETTINGS_ORG = "mymsm"
SETTINGS_APP = "MoneyBrowser"
SETTINGS_KEY_SEK_RATE = "sek_to_usd_rate"
DEFAULT_SEK_TO_USD_RATE = 0.095

TRANSACTIONS_PAGE = 0
VALUE_PAGE = 1
AMORTIZATION_PAGE = 2

ACCOUNTS_TAB = 0


class MainWindow(QMainWindow):
    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._settings = QSettings(SETTINGS_ORG, SETTINGS_APP)
        self.setWindowTitle("Money Browser")
        self.resize(1000, 600)

        self._history = NavigationHistory()
        self._current_view = None
        self._navigating_back = False
        self._undo_stack = UndoStack()
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._on_undo)
        QApplication.instance().installEventFilter(self)

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

        self._network_manager = QNetworkAccessManager(self)

        self.refresh_rate_button = QPushButton("Refresh")
        self.refresh_rate_button.clicked.connect(self._on_refresh_rate_button_clicked)

        rate_row = QHBoxLayout()
        rate_row.addWidget(QLabel("1 SEK ="))
        rate_row.addWidget(self.sek_rate_spinbox)
        rate_row.addWidget(QLabel("USD"))
        rate_row.addWidget(self.refresh_rate_button)
        rate_row.addStretch()

        self.show_closed_checkbox = QCheckBox("Show only closed accounts")
        self.show_closed_checkbox.stateChanged.connect(self._reload_accounts)

        self.new_account_button = QPushButton("New Account")
        self.new_account_button.clicked.connect(self._on_new_account_button_clicked)

        self.import_button = QPushButton("Import")
        self.import_button.clicked.connect(self._on_import_button_clicked)

        new_account_row = QHBoxLayout()
        new_account_row.addWidget(self.new_account_button)
        new_account_row.addWidget(self.import_button)

        self.account_view = QTableView()
        self.account_view.setModel(self.account_model)
        self.account_view.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        self.account_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.account_view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.account_view.selectionModel().selectionChanged.connect(self._on_account_selected)
        enable_cell_copy(self.account_view, extra_actions=self._account_context_actions)

        self.account_details_label = QLabel()
        enable_label_copy(self.account_details_label)

        self.transaction_view = QTableView()
        self.transaction_view.setModel(self.transaction_model)
        self.transaction_view.horizontalHeader().setStretchLastSection(True)
        self.transaction_view.setSortingEnabled(True)
        self.transaction_view.doubleClicked.connect(self._on_transaction_double_clicked)
        enable_cell_copy(
            self.transaction_view,
            on_edit=self._edit_transaction,
            extra_actions=self._transaction_context_actions,
        )

        self.value_chart_view = QChartView()
        self.value_chart_view.setRenderHint(QPainter.Antialiasing)

        self.amortization_chart_view = QChartView()
        self.amortization_chart_view.setRenderHint(QPainter.Antialiasing)

        self.add_record_button = QPushButton("Add Record")
        self.add_record_button.clicked.connect(self._on_add_record_button_clicked)

        self.account_details_button = QPushButton("Account Details")
        self.account_details_button.clicked.connect(self._on_account_details_button_clicked)

        self.value_checkbox = QCheckBox("Value")
        self.value_checkbox.toggled.connect(self._on_value_checkbox_toggled)

        self.amortization_checkbox = QCheckBox("Amortization")
        self.amortization_checkbox.toggled.connect(self._on_amortization_checkbox_toggled)

        header_row = QHBoxLayout()
        header_row.addWidget(self.account_details_label, 1)
        header_row.addWidget(self.add_record_button)
        header_row.addWidget(self.account_details_button)
        header_row.addWidget(self.value_checkbox)
        header_row.addWidget(self.amortization_checkbox)

        self.content_stack = QStackedWidget()
        self.content_stack.addWidget(self.transaction_view)
        self.content_stack.addWidget(self.value_chart_view)
        self.content_stack.addWidget(self.amortization_chart_view)

        transactions_page = QWidget()
        transactions_layout = QVBoxLayout(transactions_page)
        transactions_layout.addLayout(header_row)
        transactions_layout.addWidget(self.content_stack)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(self.total_label)
        left_layout.addWidget(self.show_closed_checkbox)
        left_layout.addWidget(self.account_view)
        left_layout.addLayout(rate_row)
        left_layout.addLayout(new_account_row)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(transactions_page)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        self.categories_pane = CategoriesPane(self._conn, self.statusBar().showMessage)
        self.payees_pane = PayeesPane(self._conn, self.statusBar().showMessage)
        self.investments_pane = InvestmentsPane(self._conn, self.statusBar().showMessage)

        dictionaries_tabs = QTabWidget()
        dictionaries_tabs.addTab(self.categories_pane, "Categories")
        dictionaries_tabs.addTab(self.payees_pane, "Payees")
        dictionaries_tabs.addTab(self.investments_pane, "Investments")

        self.search_pane = SearchPane(
            self._conn, self.statusBar().showMessage,
            on_transaction_changed=self._refresh_after_write,
        )

        self.reports_pane = ReportsPane(
            self._conn, self.statusBar().showMessage, to_usd=self.account_model.to_usd,
        )

        self.tabs = QTabWidget()
        self.tabs.addTab(splitter, "Accounts")
        self.tabs.addTab(dictionaries_tabs, "Dictionaries")
        self.tabs.addTab(self.search_pane, "Search")
        self.tabs.addTab(self.reports_pane, "Reports")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self.setCentralWidget(self.tabs)

        self._reload_accounts()
        self._current_view = self._capture_view()

    def _apply_exchange_rate(self):
        rate = Decimal(str(self.sek_rate_spinbox.value()))
        self.account_model.set_exchange_rates({"SEK": rate})

    def _update_total_label(self):
        self.total_label.setText(f"Total: {format_currency(self.account_model.total_usd())} USD")

    def _on_exchange_rate_changed(self, value):
        self._settings.setValue(SETTINGS_KEY_SEK_RATE, value)
        self._apply_exchange_rate()
        self._update_total_label()

    def _on_refresh_rate_button_clicked(self):
        request = QNetworkRequest(QUrl(FRANKFURTER_URL))
        request.setTransferTimeout(5000)
        reply = self._network_manager.get(request)
        self.refresh_rate_button.setEnabled(False)
        reply.finished.connect(partial(self._on_rate_reply_finished, reply))

    def _on_rate_reply_finished(self, reply):
        ok = reply.error() == QNetworkReply.NetworkError.NoError
        body = bytes(reply.readAll())
        reply.deleteLater()
        self._apply_rate_response(ok, body)

    def _apply_rate_response(self, ok, body):
        rate = None
        if ok:
            try:
                rate = parse_rate_response(body)
            except ValueError:
                rate = None
        if rate is None:
            self.statusBar().showMessage("Couldn't fetch exchange rate — using saved value.")
        else:
            self.sek_rate_spinbox.setValue(float(rate))
            self.statusBar().showMessage(f"Exchange rate updated: 1 SEK = {rate} USD")
        self.refresh_rate_button.setEnabled(True)

    def _reload_accounts(self):
        only_closed = self.show_closed_checkbox.isChecked()
        try:
            accounts = data.list_accounts(self._conn, only_closed=only_closed)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to load accounts: {exc}")
            return
        self.account_model.set_accounts(accounts)
        self.account_view.resizeColumnsToContents()
        self._update_total_label()
        self.account_details_label.setText("")
        self.transaction_model.set_transactions([])
        self.add_record_button.setEnabled(False)
        self.account_details_button.setEnabled(False)
        self.value_checkbox.setEnabled(False)
        self.value_checkbox.setChecked(False)
        self.content_stack.setCurrentIndex(TRANSACTIONS_PAGE)

    def _select_account_row(self, account_id):
        for row in range(self.account_model.rowCount()):
            if self.account_model.account_id_at(row) == account_id:
                self.account_view.selectRow(row)
                return

    def _on_account_details_button_clicked(self):
        indexes = self.account_view.selectionModel().selectedRows()
        if not indexes:
            return
        row = indexes[0].row()
        account_id, name, account_type, currency, balance, is_closed = self.account_model.account_at(
            row
        )
        opening_balance = data.get_opening_balance(self._conn, account_id)
        is_investment = account_type == INVESTMENT_ACCOUNT_TYPE
        usd_balance = self.account_model.to_usd(currency, balance)

        dialog = AccountDetailsDialog(
            conn=self._conn,
            account_id=account_id,
            name=name,
            account_type_label=account_type_label(account_type),
            currency=currency,
            opening_balance=opening_balance,
            balance_label="Value:" if is_investment else "Balance:",
            balance_text=f"{format_currency(usd_balance)} USD",
            status_text="Closed" if is_closed else "Open",
            parent=self,
        )
        if dialog.exec() != AccountDetailsDialog.Accepted:
            return
        self._reload_accounts()
        self._select_account_row(account_id)
        self.statusBar().showMessage("Account updated.")

    def _on_value_checkbox_toggled(self, checked):
        if not checked:
            self.content_stack.setCurrentIndex(TRANSACTIONS_PAGE)
            return
        if self.amortization_checkbox.isChecked():
            self.amortization_checkbox.blockSignals(True)
            self.amortization_checkbox.setChecked(False)
            self.amortization_checkbox.blockSignals(False)
        indexes = self.account_view.selectionModel().selectedRows()
        if not indexes:
            self.content_stack.setCurrentIndex(TRANSACTIONS_PAGE)
            return
        account_id, name, account_type, currency, _, _ = self.account_model.account_at(
            indexes[0].row()
        )
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
        self.content_stack.setCurrentIndex(VALUE_PAGE)

    def _on_amortization_checkbox_toggled(self, checked):
        if not checked:
            self.content_stack.setCurrentIndex(TRANSACTIONS_PAGE)
            return
        if self.value_checkbox.isChecked():
            self.value_checkbox.blockSignals(True)
            self.value_checkbox.setChecked(False)
            self.value_checkbox.blockSignals(False)
        indexes = self.account_view.selectionModel().selectedRows()
        if not indexes:
            self.content_stack.setCurrentIndex(TRANSACTIONS_PAGE)
            return
        account_id, name, account_type, currency, _, _ = self.account_model.account_at(
            indexes[0].row()
        )
        opening_balance = data.get_opening_balance(self._conn, account_id)
        try:
            transactions = data.list_transactions(self._conn, account_id)
            loan_terms = data.get_loan_terms(self._conn, account_id)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to load amortization schedule: {exc}")
            return
        if loan_terms is None or loan_terms[0] is None or not loan_terms[1]:
            self.content_stack.setCurrentIndex(TRANSACTIONS_PAGE)
            return
        interest_rate, payment_amount, _payment_count = loan_terms

        history = compute_account_value_history(transactions, opening_balance, is_investment=False)
        usd_history = [
            (txn_date, self.account_model.to_usd(currency, value)) for txn_date, value in history
        ]
        if usd_history:
            last_date, current_balance = usd_history[-1]
        else:
            last_date = date.today()
            current_balance = self.account_model.to_usd(currency, opening_balance or Decimal("0"))

        payments_per_year = infer_payments_per_year([txn_date for txn_date, _ in usd_history])
        inputs = AmortizationInputs(
            current_balance=current_balance,
            annual_rate=interest_rate,
            payment_amount=self.account_model.to_usd(currency, payment_amount),
            payments_per_year=payments_per_year,
            start_date=last_date,
        )
        future_points = compute_future_amortization(inputs)

        if future_points is None:
            self.statusBar().showMessage(
                "This loan's payment doesn't cover its interest — no projected payoff is possible."
            )
            chart = build_line_chart(
                f"{name} — Amortization (USD)", [("Actual", usd_history)], mark_zero=True
            )
        else:
            projected = [(last_date, current_balance)] + [
                (point.point_date, point.balance) for point in future_points
            ]
            chart = build_line_chart(
                f"{name} — Amortization (USD)",
                [("Actual", usd_history), ("Projected", projected)],
                mark_zero=True,
            )
        self.amortization_chart_view.setChart(chart)
        self.content_stack.setCurrentIndex(AMORTIZATION_PAGE)

    def _refresh_after_write(self):
        self._reload_accounts()
        self.categories_pane._reload()
        self.payees_pane._reload()
        self.investments_pane._reload()

    def _on_undo(self):
        command = self._undo_stack.pop()
        if command is None:
            self.statusBar().showMessage("Nothing to undo.")
            return
        try:
            command.undo(self._conn)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to undo: {exc}")
            return
        self._refresh_after_write()
        self.statusBar().showMessage(f"Undone: {command.description}")

    def _on_add_record_button_clicked(self):
        indexes = self.account_view.selectionModel().selectedRows()
        if not indexes:
            return
        row = indexes[0].row()
        account_id, _name, account_type, _currency, _balance, _is_closed = self.account_model.account_at(
            row
        )
        dialog = AddRecordDialog(self._conn, account_id, account_type, parent=self)
        if dialog.exec() != AddRecordDialog.Accepted:
            return
        self._undo_stack.push(AddCommand(dialog.transaction_id))
        self._refresh_after_write()
        self.account_view.selectRow(row)
        self._on_account_selected()
        self.statusBar().showMessage("Record added.")

    def _on_new_account_button_clicked(self):
        dialog = AddAccountDialog(self._conn, parent=self)
        if dialog.exec() != AddAccountDialog.Accepted:
            return
        self._reload_accounts()
        self.statusBar().showMessage("Account added.")

    def _on_import_button_clicked(self):
        file_path, _filter = QFileDialog.getOpenFileName(
            self, "Import QFX File", "", "QFX Files (*.qfx);;All Files (*)"
        )
        if not file_path:
            return
        try:
            records = parse_qfx(file_path)
        except OSError as exc:
            self.statusBar().showMessage(f"Failed to read QFX file: {exc}")
            return
        if not records:
            self.statusBar().showMessage("No transactions found in QFX file.")
            return

        selected_rows = self.account_view.selectionModel().selectedRows()
        default_account_id = (
            self.account_model.account_at(selected_rows[0].row())[0] if selected_rows else None
        )
        dialog = ImportQfxDialog(
            self._conn, records, default_account_id=default_account_id, parent=self
        )
        if dialog.exec() != ImportQfxDialog.Accepted:
            return
        if dialog.imported_transaction_ids:
            self._undo_stack.push(ImportCommand(dialog.imported_transaction_ids))
        self._refresh_after_write()
        self.statusBar().showMessage(f"Imported {dialog.imported_count} transaction(s).")

    def _on_toggle_closed_button_clicked(self, row):
        account_id, name, _account_type, _currency, _balance, is_closed = self.account_model.account_at(
            row
        )
        if not is_closed:
            reply = QMessageBox.question(
                self,
                "Close Account",
                f"Close '{name}'?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return
        writes.set_account_closed(self._conn, account_id, not is_closed)
        self._reload_accounts()
        self.statusBar().showMessage("Account reopened." if is_closed else "Account closed.")

    def _account_context_actions(self, row):
        _account_id, _name, _account_type, _currency, _balance, is_closed = self.account_model.account_at(
            row
        )
        if not is_closed:
            return [("Close Account", partial(self._on_toggle_closed_button_clicked, row))]
        return [
            ("Reopen Account", partial(self._on_toggle_closed_button_clicked, row)),
            ("Delete Account", partial(self._on_delete_account_clicked, row)),
        ]

    def _on_delete_account_clicked(self, row):
        account_id, name, _account_type, _currency, _balance, _is_closed = self.account_model.account_at(
            row
        )
        transaction_count = len(data.list_transactions(self._conn, account_id))
        reply = QMessageBox.question(
            self,
            "Delete Account",
            f"Permanently delete '{name}' and its {transaction_count} transaction(s)? "
            "This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        writes.delete_account(self._conn, account_id)
        self._undo_stack = UndoStack()
        self._refresh_after_write()
        self.statusBar().showMessage(f"Account '{name}' deleted.")

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
        if transaction[0] is None:
            self.statusBar().showMessage(
                "Interest records are derived from another account and can't be edited here."
            )
            return
        before_row = data.get_transaction_row(self._conn, transaction[0])
        dialog = AddRecordDialog(self._conn, account_id, account_type, transaction=transaction, parent=self)
        if dialog.exec() != AddRecordDialog.Accepted:
            return
        self._undo_stack.push(EditCommand(before_row))
        self._refresh_after_write()
        self.account_view.selectRow(account_row)
        self._on_account_selected()
        self.statusBar().showMessage("Record updated.")

    def _transaction_context_actions(self, row):
        if self.transaction_model.transaction_at(row)[0] is None:
            return []
        return [("Delete Record", partial(self._on_delete_record_clicked, row))]

    def _on_delete_record_clicked(self, row):
        indexes = self.account_view.selectionModel().selectedRows()
        if not indexes:
            return
        account_row = indexes[0].row()
        transaction_id = self.transaction_model.transaction_at(row)[0]
        reply = QMessageBox.question(
            self,
            "Delete Record",
            "Permanently delete this record? Press Ctrl+Z afterward to undo.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return
        before_row = data.get_transaction_row(self._conn, transaction_id)
        writes.delete_transaction(self._conn, transaction_id)
        self._undo_stack.push(DeleteCommand(before_row))
        self._refresh_after_write()
        self.account_view.selectRow(account_row)
        self._on_account_selected()
        self.statusBar().showMessage("Record deleted.")

    def eventFilter(self, obj, event):
        if event.type() == QEvent.MouseButtonPress and event.button() == Qt.BackButton:
            self._go_back()
            return True
        return super().eventFilter(obj, event)

    def _capture_view(self):
        tab_index = self.tabs.currentIndex()
        account_id = None
        if tab_index == ACCOUNTS_TAB:
            indexes = self.account_view.selectionModel().selectedRows()
            if indexes:
                account_id = self.account_model.account_id_at(indexes[0].row())
        return (tab_index, account_id)

    def _maybe_record_view_change(self):
        new_view = self._capture_view()
        if new_view == self._current_view:
            return
        if not self._navigating_back and self._current_view is not None:
            self._history.push(self._current_view)
        self._current_view = new_view

    def _on_tab_changed(self, index):
        self._maybe_record_view_change()

    def _go_back(self):
        view = self._history.pop()
        if view is None:
            return
        self._navigating_back = True
        try:
            tab_index, account_id = view
            self.tabs.setCurrentIndex(tab_index)
            if tab_index == ACCOUNTS_TAB and account_id is not None:
                self._select_account_row(account_id)
        finally:
            self._navigating_back = False
        self._current_view = view

    def _on_account_selected(self, selected=None, deselected=None):
        self._maybe_record_view_change()
        indexes = self.account_view.selectionModel().selectedRows()
        has_selection = bool(indexes)
        self.add_record_button.setEnabled(has_selection)
        self.account_details_button.setEnabled(has_selection)
        self.value_checkbox.setEnabled(has_selection)
        self.value_checkbox.setChecked(False)
        self.amortization_checkbox.setEnabled(False)
        self.amortization_checkbox.setChecked(False)
        self.amortization_checkbox.setToolTip("")
        self.content_stack.setCurrentIndex(TRANSACTIONS_PAGE)
        if not indexes:
            self.account_details_label.setText("")
            self.transaction_model.set_transactions([])
            return
        account_id, name, account_type, currency, balance, _ = self.account_model.account_at(
            indexes[0].row()
        )
        is_investment = account_type == INVESTMENT_ACCOUNT_TYPE
        is_loan = account_type == LOAN_ACCOUNT_TYPE
        balance_label = "Value" if is_investment else "Balance"
        usd_balance = self.account_model.to_usd(currency, balance)
        try:
            transactions = data.list_transactions(self._conn, account_id)
            if is_loan:
                interest_payments = data.list_loan_interest_payments(self._conn, account_id)
        except Exception as exc:
            self.statusBar().showMessage(f"Failed to load transactions: {exc}")
            return
        loan_terms = None
        if is_loan:
            try:
                loan_terms = data.get_loan_terms(self._conn, account_id)
            except Exception:
                loan_terms = None
        if is_loan:
            has_amortization = (
                loan_terms is not None
                and loan_terms[0] is not None
                and loan_terms[1] is not None
                and loan_terms[1] > 0
            )
            self.amortization_checkbox.setEnabled(has_amortization)
            if not has_amortization:
                self.amortization_checkbox.setToolTip(
                    "No interest rate/payment data available for this loan."
                )
            display_rows = build_loan_transaction_rows(transactions, interest_payments)
            principal_total, usd_interest = compute_loan_totals(
                transactions, interest_payments, self.account_model.to_usd
            )
            usd_principal = self.account_model.to_usd(currency, principal_total)
            self.account_details_label.setText(
                f"{name} ({account_type_label(account_type)}) — "
                f"{balance_label}: {format_currency(usd_balance)} USD — "
                f"Total Principal Paid: {format_currency(usd_principal)} USD — "
                f"Total Interest Paid: {format_currency(usd_interest)} USD — "
                f"{len(display_rows)} record(s)"
            )
            self.transaction_model.set_transactions(display_rows, is_loan=True)
        else:
            self.account_details_label.setText(
                f"{name} ({account_type_label(account_type)}) — "
                f"{balance_label}: {format_currency(usd_balance)} USD — "
                f"{len(transactions)} record(s)"
            )
            self.transaction_model.set_transactions(transactions, is_investment=is_investment)
        self.transaction_view.resizeColumnsToContents()
