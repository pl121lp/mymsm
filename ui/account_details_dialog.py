"""Modal dialog for viewing and editing an account's details."""

from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QFormLayout, QLabel, QLineEdit, QVBoxLayout

import writes
from table_copy import enable_label_copy


def _parse_decimal(text):
    text = text.strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


class AccountDetailsDialog(QDialog):
    """Shows an account's details; name and starting balance are editable."""

    def __init__(
        self,
        conn,
        account_id,
        name,
        account_type_label,
        currency,
        opening_balance,
        balance_label,
        balance_text,
        status_text,
        parent=None,
    ):
        super().__init__(parent)
        self._conn = conn
        self._account_id = account_id
        self.setWindowTitle("Account Details")

        self.name_edit = QLineEdit(name)
        self.type_value = QLabel(account_type_label)
        self.currency_value = QLabel(currency)
        self.opening_balance_edit = QLineEdit(
            str(opening_balance) if opening_balance is not None else "0"
        )
        self.balance_label = QLabel(balance_label)
        self.balance_value = QLabel(balance_text)
        self.status_value = QLabel(status_text)
        for value_label in (self.type_value, self.currency_value, self.balance_value, self.status_value):
            enable_label_copy(value_label)

        form = QFormLayout()
        form.addRow("Name:", self.name_edit)
        form.addRow("Type:", self.type_value)
        form.addRow("Currency:", self.currency_value)
        form.addRow("Starting balance:", self.opening_balance_edit)
        form.addRow(self.balance_label, self.balance_value)
        form.addRow("Status:", self.status_value)
        form.setAlignment(Qt.AlignTop)

        self.error_label = QLabel()
        self.error_label.setStyleSheet("color: red;")
        self.error_label.setWordWrap(True)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self._on_accept)
        self.button_box.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.addLayout(form)
        layout.addWidget(self.error_label)
        layout.addWidget(self.button_box)

        self.name_edit.textChanged.connect(self._validate)
        self.opening_balance_edit.textChanged.connect(self._validate)

        self._validate()

    def _validate(self):
        valid = (
            bool(self.name_edit.text().strip())
            and _parse_decimal(self.opening_balance_edit.text()) is not None
        )
        self.button_box.button(QDialogButtonBox.Save).setEnabled(valid)

    def _on_accept(self):
        try:
            writes.update_account(
                self._conn,
                self._account_id,
                name=self.name_edit.text().strip(),
                opening_balance=_parse_decimal(self.opening_balance_edit.text()),
            )
        except Exception as exc:
            self.error_label.setText(f"Failed to update account: {exc}")
            return
        self.accept()
