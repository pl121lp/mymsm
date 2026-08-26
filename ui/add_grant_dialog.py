"""Modal dialog for adding a new RSU grant (a Grant transaction plus its
full quarterly-or-otherwise vesting schedule) to an investment account."""

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
    QSpinBox,
    QVBoxLayout,
)

import data
import writes

FREQUENCY_CHOICES = [("Month", 1), ("Quarter", 3), ("Year", 12)]


class AddGrantDialog(QDialog):
    """Adds a Grant (activity 17) transaction for the entered total shares,
    plus one Vested (activity 18) transaction per vesting event, evenly
    splitting the shares (the last vest absorbs any rounding remainder)."""

    def __init__(self, conn, account_id, parent=None):
        super().__init__(parent)
        self._conn = conn
        self._account_id = account_id
        self.transaction_ids = None

        self.setWindowTitle("Add Grant")

        self.security_edit = QLineEdit()
        completer = QCompleter([name for _id, name in self._security_names()])
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.security_edit.setCompleter(completer)

        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)

        self.total_shares_spin = QSpinBox()
        self.total_shares_spin.setRange(1, 10_000_000)
        self.total_shares_spin.setValue(100)

        self.frequency_combo = QComboBox()
        for label, months in FREQUENCY_CHOICES:
            self.frequency_combo.addItem(label, months)
        self.frequency_combo.setCurrentIndex(1)  # Quarter

        self.vest_count_spin = QSpinBox()
        self.vest_count_spin.setRange(1, 100)
        self.vest_count_spin.setValue(12)

        form = QFormLayout()
        form.addRow("Grant Name:", self.security_edit)
        form.addRow("Grant Date:", self.date_edit)
        form.addRow("Total Shares:", self.total_shares_spin)
        form.addRow("Vests Every:", self.frequency_combo)
        form.addRow("Number of Vests:", self.vest_count_spin)

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

        self.security_edit.textChanged.connect(self._validate)
        self._validate()

    def _security_names(self):
        try:
            return data.list_securities(self._conn)
        except Exception:
            return []

    def _validate(self):
        valid = bool(self.security_edit.text().strip())
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(valid)

    def _on_accept(self):
        try:
            self.transaction_ids = writes.add_rsu_grant(
                self._conn,
                self._account_id,
                security_name=self.security_edit.text().strip(),
                grant_date=self.date_edit.date().toPython(),
                total_shares=self.total_shares_spin.value(),
                vest_frequency_months=self.frequency_combo.currentData(),
                vest_count=self.vest_count_spin.value(),
            )
        except Exception as exc:
            self.error_label.setText(f"Failed to add grant: {exc}")
            return
        self.accept()
