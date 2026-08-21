"""Search tab: filter transactions across all accounts by payee, category,
investment, memo text, amount range, and/or account."""

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSplitter,
    QTableView,
    QVBoxLayout,
    QWidget,
)

import data
from add_record_dialog import AddRecordDialog
from models import SearchResultTableModel
from table_copy import enable_cell_copy

# Sentinel "no bound" date for the min/max date filters: shown as the
# specialValueText "Any" whenever a QDateEdit is left at its minimum.
NO_DATE_BOUND = QDate(1900, 1, 1)


def _parse_decimal(text):
    text = text.strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def _make_optional_date_edit():
    date_edit = QDateEdit()
    date_edit.setCalendarPopup(True)
    date_edit.setMinimumDate(NO_DATE_BOUND)
    date_edit.setSpecialValueText("Any")
    date_edit.setDate(NO_DATE_BOUND)
    return date_edit


def _date_bound(date_edit):
    return None if date_edit.date() == NO_DATE_BOUND else date_edit.date().toPython()


class SearchPane(QWidget):
    def __init__(self, conn, report_error, on_transaction_changed=None, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._report_error = report_error
        self._on_transaction_changed = on_transaction_changed

        self.payee_edit = QLineEdit()
        self.category_edit = QLineEdit()
        self.investment_edit = QLineEdit()
        self.memo_edit = QLineEdit()
        self.amount_min_edit = QLineEdit()
        self.amount_min_edit.setPlaceholderText("min")
        self.amount_max_edit = QLineEdit()
        self.amount_max_edit.setPlaceholderText("max")

        self.date_min_edit = _make_optional_date_edit()
        self.date_max_edit = _make_optional_date_edit()

        self.account_list = QListWidget()
        self.account_list.setSelectionMode(QAbstractItemView.ExtendedSelection)

        self.search_button = QPushButton("Search")
        self.search_button.clicked.connect(self._on_search_clicked)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self._on_clear_clicked)

        amount_row = QHBoxLayout()
        amount_row.addWidget(self.amount_min_edit)
        amount_row.addWidget(QLabel("–"))
        amount_row.addWidget(self.amount_max_edit)

        date_row = QHBoxLayout()
        date_row.addWidget(self.date_min_edit)
        date_row.addWidget(QLabel("–"))
        date_row.addWidget(self.date_max_edit)

        button_row = QHBoxLayout()
        button_row.addWidget(self.search_button)
        button_row.addWidget(self.clear_button)
        button_row.addStretch()

        filters_form = QFormLayout()
        filters_form.addRow("Payee:", self.payee_edit)
        filters_form.addRow("Category:", self.category_edit)
        filters_form.addRow("Investment:", self.investment_edit)
        filters_form.addRow("Memo:", self.memo_edit)
        filters_form.addRow("Amount:", amount_row)
        filters_form.addRow("Date:", date_row)

        filters = QWidget()
        filters_layout = QVBoxLayout(filters)
        filters_layout.setContentsMargins(0, 0, 0, 0)
        filters_layout.addLayout(filters_form)
        filters_layout.addWidget(QLabel("Accounts:"))
        filters_layout.addWidget(self.account_list)
        filters_layout.addLayout(button_row)

        self.result_model = SearchResultTableModel()
        self.result_view = QTableView()
        self.result_view.setModel(self.result_model)
        self.result_view.horizontalHeader().setStretchLastSection(True)
        self.result_view.doubleClicked.connect(self._on_result_double_clicked)
        enable_cell_copy(self.result_view, on_edit=self._edit_result)

        self.result_count_label = QLabel()

        results = QWidget()
        results_layout = QVBoxLayout(results)
        results_layout.setContentsMargins(0, 0, 0, 0)
        results_layout.addWidget(self.result_count_label)
        results_layout.addWidget(self.result_view)

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(filters)
        splitter.addWidget(results)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

        self._reload_accounts()

    def _reload_accounts(self):
        try:
            accounts = data.list_accounts(self._conn, include_closed=True)
        except Exception as exc:
            self._report_error(f"Failed to load accounts: {exc}")
            return
        self.account_list.clear()
        for account_id, name, *_rest in accounts:
            item = QListWidgetItem(name)
            item.setData(Qt.UserRole, account_id)
            self.account_list.addItem(item)

    def _selected_account_ids(self):
        return [item.data(Qt.UserRole) for item in self.account_list.selectedItems()]

    def _run_search(self):
        try:
            results = data.search_transactions(
                self._conn,
                payee=self.payee_edit.text().strip() or None,
                category=self.category_edit.text().strip() or None,
                investment=self.investment_edit.text().strip() or None,
                memo=self.memo_edit.text().strip() or None,
                amount_min=_parse_decimal(self.amount_min_edit.text()),
                amount_max=_parse_decimal(self.amount_max_edit.text()),
                date_min=_date_bound(self.date_min_edit),
                date_max=_date_bound(self.date_max_edit),
                account_ids=self._selected_account_ids() or None,
            )
        except Exception as exc:
            self._report_error(f"Search failed: {exc}")
            return
        self.result_model.set_results(results)
        self.result_view.resizeColumnsToContents()
        count = len(results)
        self.result_count_label.setText(f"{count} matching transaction{'' if count == 1 else 's'}")

    def _on_search_clicked(self):
        self._run_search()

    def _on_clear_clicked(self):
        for edit in (
            self.payee_edit, self.category_edit, self.investment_edit,
            self.memo_edit, self.amount_min_edit, self.amount_max_edit,
        ):
            edit.clear()
        self.date_min_edit.setDate(NO_DATE_BOUND)
        self.date_max_edit.setDate(NO_DATE_BOUND)
        self.account_list.clearSelection()
        self.result_model.set_results([])
        self.result_count_label.setText("")

    def _on_result_double_clicked(self, index):
        self._edit_result(index.row())

    def _edit_result(self, row):
        account_id, account_type = self.result_model.account_info_at(row)
        transaction = self.result_model.transaction_at(row)
        dialog = AddRecordDialog(self._conn, account_id, account_type, transaction=transaction, parent=self)
        if dialog.exec() != AddRecordDialog.Accepted:
            return
        if self._on_transaction_changed:
            self._on_transaction_changed()
        self._run_search()
        self._report_error("Record updated.")
