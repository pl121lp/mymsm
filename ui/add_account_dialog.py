"""Modal dialog for adding a new account."""

from decimal import Decimal, InvalidOperation

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

import writes
from models import ACCOUNT_TYPE_LABELS


def _parse_decimal(text):
    text = text.strip()
    if not text:
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


class AddAccountDialog(QDialog):
    """Creates a new account (open by default)."""

    def __init__(self, conn, parent=None):
        super().__init__(parent)
        self._conn = conn
        self.account_id = None

        self.setWindowTitle("New Account")

        self.name_edit = QLineEdit()

        self.type_combo = QComboBox()
        for account_type, label in ACCOUNT_TYPE_LABELS.items():
            self.type_combo.addItem(label, account_type)

        self.currency_edit = QLineEdit("USD")

        self.opening_balance_edit = QLineEdit("0")

        form = QFormLayout()
        form.addRow("Name:", self.name_edit)
        form.addRow("Type:", self.type_combo)
        form.addRow("Currency:", self.currency_edit)
        form.addRow("Opening balance:", self.opening_balance_edit)

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

        self.name_edit.textChanged.connect(self._validate)
        self.opening_balance_edit.textChanged.connect(self._validate)

        self._validate()

    def _validate(self):
        valid = (
            bool(self.name_edit.text().strip())
            and _parse_decimal(self.opening_balance_edit.text()) is not None
        )
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(valid)

    def _on_accept(self):
        try:
            self.account_id = writes.add_account(
                self._conn,
                name=self.name_edit.text().strip(),
                account_type=self.type_combo.currentData(),
                currency=self.currency_edit.text().strip() or "USD",
                opening_balance=_parse_decimal(self.opening_balance_edit.text()),
            )
        except Exception as exc:
            self.error_label.setText(f"Failed to add account: {exc}")
            return
        self.accept()
