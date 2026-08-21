"""Modal dialog for adding a new transaction to an account."""

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import QDate, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QCompleter,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

import data
import writes
from data import BUY_ACTIVITY, INVESTMENT_ACCOUNT_TYPE, SELL_ACTIVITY

ACTIVITY_CHOICES = [("Buy", BUY_ACTIVITY), ("Sell", SELL_ACTIVITY)]


def _make_completer(names):
    completer = QCompleter(names)
    completer.setCaseSensitivity(Qt.CaseInsensitive)
    completer.setFilterMode(Qt.MatchContains)
    return completer


def _parse_decimal(text):
    text = text.strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


class AddRecordDialog(QDialog):
    """Add a transaction to `account_id`. Cash accounts get Payee/Category
    fields; investment accounts (account_type == INVESTMENT_ACCOUNT_TYPE)
    get Security/Activity/Quantity/Price fields instead."""

    def __init__(self, conn, account_id, account_type, transaction=None, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._account_id = account_id
        self._is_investment = account_type == INVESTMENT_ACCOUNT_TYPE
        self._editing_transaction_id = transaction[0] if transaction else None
        self.transaction_id = self._editing_transaction_id

        self.setWindowTitle("Edit Record" if transaction else "Add Record")

        self.date_edit = QDateEdit()
        txn_date = transaction[1] if transaction else None
        self.date_edit.setDate(QDate(txn_date.year, txn_date.month, txn_date.day) if txn_date else QDate.currentDate())
        self.date_edit.setCalendarPopup(True)

        self.amount_edit = QLineEdit()
        self.amount_edit.setPlaceholderText("e.g. -52.30")
        if transaction:
            self.amount_edit.setText(str(transaction[5]))

        self.memo_edit = QLineEdit()
        if transaction:
            self.memo_edit.setText(transaction[4] or "")

        form = QFormLayout()
        form.addRow("Date:", self.date_edit)

        if self._is_investment:
            self.security_edit = QLineEdit()
            self.security_edit.setCompleter(_make_completer(self._dictionary_names(data.list_securities)))
            self.activity_combo = QComboBox()
            for label, code in ACTIVITY_CHOICES:
                self.activity_combo.addItem(label, code)
            self.quantity_edit = QLineEdit()
            self.price_edit = QLineEdit()
            if transaction:
                self.security_edit.setText(transaction[6] or "")
                activity_index = self.activity_combo.findData(transaction[7])
                if activity_index >= 0:
                    self.activity_combo.setCurrentIndex(activity_index)
                if transaction[8] is not None:
                    self.quantity_edit.setText(str(transaction[8]))
                if transaction[9] is not None:
                    self.price_edit.setText(str(transaction[9]))
            form.addRow("Security:", self.security_edit)
            form.addRow("Activity:", self.activity_combo)
            form.addRow("Quantity:", self.quantity_edit)
            form.addRow("Price:", self.price_edit)
        else:
            self.payee_edit = QLineEdit()
            self.payee_edit.setCompleter(_make_completer(self._dictionary_names(data.list_payees)))
            self.category_edit = QLineEdit()
            self.category_edit.setCompleter(_make_completer(self._dictionary_names(data.list_categories)))
            if transaction:
                self.payee_edit.setText(transaction[2] or "")
                self.category_edit.setText(transaction[3] or "")
            form.addRow("Payee:", self.payee_edit)
            form.addRow("Category:", self.category_edit)

        form.addRow("Amount:", self.amount_edit)
        form.addRow("Memo:", self.memo_edit)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        self.error_label.setWordWrap(True)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addWidget(self.button_box)

        self.amount_edit.textChanged.connect(self._validate)
        if self._is_investment:
            self.security_edit.textChanged.connect(self._validate)
            self.quantity_edit.textChanged.connect(self._validate)
            self.price_edit.textChanged.connect(self._validate)

        self._validate()

    def _dictionary_names(self, list_fn):
        try:
            return [name for _id, name in list_fn(self._conn)]
        except Exception:
            return []

    def _validate(self):
        valid = _parse_decimal(self.amount_edit.text()) is not None
        if self._is_investment:
            valid = (
                valid
                and bool(self.security_edit.text().strip())
                and _parse_decimal(self.quantity_edit.text()) is not None
                and _parse_decimal(self.price_edit.text()) is not None
            )
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(valid)

    def _on_accept(self):
        amount = _parse_decimal(self.amount_edit.text())
        memo = self.memo_edit.text().strip() or None
        if self._is_investment:
            kwargs = dict(
                security_name=self.security_edit.text().strip() or None,
                activity=self.activity_combo.currentData(),
                quantity=_parse_decimal(self.quantity_edit.text()),
                price=_parse_decimal(self.price_edit.text()),
            )
        else:
            kwargs = dict(
                payee_name=self.payee_edit.text().strip() or None,
                category_name=self.category_edit.text().strip() or None,
            )

        try:
            if self._editing_transaction_id is not None:
                self.transaction_id = writes.update_transaction(
                    self._conn,
                    self._editing_transaction_id,
                    self.date_edit.date().toPython(),
                    amount,
                    memo=memo,
                    **kwargs,
                )
            else:
                self.transaction_id = writes.add_transaction(
                    self._conn,
                    self._account_id,
                    self.date_edit.date().toPython(),
                    amount,
                    memo=memo,
                    **kwargs,
                )
        except Exception as exc:
            action = "update" if self._editing_transaction_id is not None else "add"
            self.error_label.setText(f"Failed to {action} record: {exc}")
            return
        self.accept()
