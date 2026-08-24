"""Controls panel for the College Tuition Projection report: college
savings account selection, expected investment return, a joint quarterly
contribution, and per-person (Person 1 / Person 2) tuition/housing/
timeline inputs, laid out in labeled sections with an Update button.
"""

from datetime import date
from decimal import Decimal

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from category_filter_dialog import AccountFilterDialog
from form_controls import dollar_spinbox, percent_spinbox, year_spinbox


def default_college_tuition_values(today=None):
    """Built-in defaults for a first-time (no saved settings) load."""
    today = today or date.today()
    return {
        "annual_return_rate": 6.0,
        "contribution_per_quarter": 0.0,
        "contribution_end_year": today.year + 12,
        "person1_start_year": today.year + 5,
        "person1_end_year": today.year + 9,
        "person1_tuition_per_quarter": 10000.0,
        "person1_housing_per_quarter": 4000.0,
        "person2_start_year": today.year + 8,
        "person2_end_year": today.year + 12,
        "person2_tuition_per_quarter": 10000.0,
        "person2_housing_per_quarter": 4000.0,
    }


class CollegeTuitionControlsPanel(QWidget):
    updated = Signal()

    def __init__(self, parent=None, today=None):
        super().__init__(parent)
        defaults = default_college_tuition_values(today)

        self._accounts = []
        self._balances = {}
        self._selected_account_ids = None

        self.starting_fund_value_spinbox = dollar_spinbox(0.0)
        self.starting_fund_value_spinbox.setEnabled(False)
        self.starting_fund_value_spinbox.setToolTip(
            "Sum of the selected College Savings Accounts; not editable."
        )
        self.select_accounts_button = QPushButton("Select Accounts...")
        self.select_accounts_button.clicked.connect(self._on_select_accounts_clicked)

        self.annual_return_rate_spinbox = percent_spinbox(defaults["annual_return_rate"])

        self.contribution_per_quarter_spinbox = dollar_spinbox(defaults["contribution_per_quarter"])
        self.contribution_end_year_spinbox = year_spinbox(defaults["contribution_end_year"])

        self.person1_start_year_spinbox = year_spinbox(defaults["person1_start_year"])
        self.person1_end_year_spinbox = year_spinbox(defaults["person1_end_year"])
        self.person1_tuition_per_quarter_spinbox = dollar_spinbox(defaults["person1_tuition_per_quarter"])
        self.person1_housing_per_quarter_spinbox = dollar_spinbox(defaults["person1_housing_per_quarter"])

        self.person2_start_year_spinbox = year_spinbox(defaults["person2_start_year"])
        self.person2_end_year_spinbox = year_spinbox(defaults["person2_end_year"])
        self.person2_tuition_per_quarter_spinbox = dollar_spinbox(defaults["person2_tuition_per_quarter"])
        self.person2_housing_per_quarter_spinbox = dollar_spinbox(defaults["person2_housing_per_quarter"])

        self.update_button = QPushButton("Update")
        self.update_button.clicked.connect(self.updated.emit)

        layout = QVBoxLayout(self)

        accounts_form = QFormLayout()
        accounts_form.addRow("College savings total:", self.starting_fund_value_spinbox)
        accounts_row = QHBoxLayout()
        accounts_row.addWidget(self.select_accounts_button)
        accounts_row.addStretch()

        returns_form = QFormLayout()
        returns_form.addRow("Expected yearly return:", self.annual_return_rate_spinbox)

        contribution_form = QFormLayout()
        contribution_form.addRow("Joint contribution per quarter:", self.contribution_per_quarter_spinbox)
        contribution_form.addRow("Contribution end year:", self.contribution_end_year_spinbox)

        person1_form = QFormLayout()
        person1_form.addRow("Start year:", self.person1_start_year_spinbox)
        person1_form.addRow("End year:", self.person1_end_year_spinbox)
        person1_form.addRow("Tuition per quarter:", self.person1_tuition_per_quarter_spinbox)
        person1_form.addRow("Housing per quarter:", self.person1_housing_per_quarter_spinbox)

        person2_form = QFormLayout()
        person2_form.addRow("Start year:", self.person2_start_year_spinbox)
        person2_form.addRow("End year:", self.person2_end_year_spinbox)
        person2_form.addRow("Tuition per quarter:", self.person2_tuition_per_quarter_spinbox)
        person2_form.addRow("Housing per quarter:", self.person2_housing_per_quarter_spinbox)

        layout.addWidget(QLabel("<b>College Savings Accounts</b>"))
        layout.addLayout(accounts_form)
        layout.addLayout(accounts_row)
        layout.addWidget(QLabel("<b>Investment Return</b>"))
        layout.addLayout(returns_form)
        layout.addWidget(QLabel("<b>Contribution</b>"))
        layout.addLayout(contribution_form)
        layout.addWidget(QLabel("<b>Person 1</b>"))
        layout.addLayout(person1_form)
        layout.addWidget(QLabel("<b>Person 2</b>"))
        layout.addLayout(person2_form)
        layout.addWidget(self.update_button)
        layout.addStretch()

    def set_accounts(self, accounts, balances):
        """accounts: iterable of (account_id, name) Investment-type pairs.
        balances: dict of account_id -> Decimal USD value. Recomputes the
        read-only starting fund value display; selects every account the
        first time this is called (selection unset), and thereafter keeps
        only the intersection of the current selection with the accounts
        given (an account removed/closed since drops out silently).
        """
        self._accounts = list(accounts)
        self._balances = dict(balances)
        known_ids = {account_id for account_id, _name in self._accounts}
        if self._selected_account_ids is None:
            self._selected_account_ids = set(known_ids)
        else:
            self._selected_account_ids &= known_ids
        self._update_starting_fund_value()

    def _update_starting_fund_value(self):
        total = sum(
            (self._balances.get(account_id, Decimal("0")) for account_id in self._selected_account_ids),
            start=Decimal("0"),
        )
        self.starting_fund_value_spinbox.setValue(float(total))

    def _on_select_accounts_clicked(self):
        dialog = AccountFilterDialog(self._accounts, self._selected_account_ids or set(), self)
        if dialog.exec() != QDialog.Accepted:
            return
        self._selected_account_ids = dialog.selected_account_ids()
        self._update_starting_fund_value()

    def values(self):
        return {
            "starting_fund_value": self.starting_fund_value_spinbox.value(),
            "selected_account_ids": sorted(self._selected_account_ids or []),
            "annual_return_rate": self.annual_return_rate_spinbox.value(),
            "contribution_per_quarter": self.contribution_per_quarter_spinbox.value(),
            "contribution_end_year": self.contribution_end_year_spinbox.value(),
            "person1_start_year": self.person1_start_year_spinbox.value(),
            "person1_end_year": self.person1_end_year_spinbox.value(),
            "person1_tuition_per_quarter": self.person1_tuition_per_quarter_spinbox.value(),
            "person1_housing_per_quarter": self.person1_housing_per_quarter_spinbox.value(),
            "person2_start_year": self.person2_start_year_spinbox.value(),
            "person2_end_year": self.person2_end_year_spinbox.value(),
            "person2_tuition_per_quarter": self.person2_tuition_per_quarter_spinbox.value(),
            "person2_housing_per_quarter": self.person2_housing_per_quarter_spinbox.value(),
        }

    def set_values(self, values):
        widgets = {
            "annual_return_rate": self.annual_return_rate_spinbox,
            "contribution_per_quarter": self.contribution_per_quarter_spinbox,
            "contribution_end_year": self.contribution_end_year_spinbox,
            "person1_start_year": self.person1_start_year_spinbox,
            "person1_end_year": self.person1_end_year_spinbox,
            "person1_tuition_per_quarter": self.person1_tuition_per_quarter_spinbox,
            "person1_housing_per_quarter": self.person1_housing_per_quarter_spinbox,
            "person2_start_year": self.person2_start_year_spinbox,
            "person2_end_year": self.person2_end_year_spinbox,
            "person2_tuition_per_quarter": self.person2_tuition_per_quarter_spinbox,
            "person2_housing_per_quarter": self.person2_housing_per_quarter_spinbox,
        }
        for key, widget in widgets.items():
            if key not in values:
                continue
            try:
                widget.setValue(values[key])
            except TypeError:
                continue
        if "selected_account_ids" in values:
            known_ids = {account_id for account_id, _name in self._accounts}
            self._selected_account_ids = set(values["selected_account_ids"]) & known_ids
            self._update_starting_fund_value()
