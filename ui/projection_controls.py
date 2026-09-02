"""Controls panel for the Net Worth Projection report: birth year,
retirement age, investment returns, income/spending, tax, inflation,
Social Security, house sale, inheritance, and retirement medical cost
inputs, laid out in labeled sections with an Update button.
"""

from datetime import date

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from form_controls import dollar_spinbox, percent_spinbox, year_spinbox
from projection_settings import DEFAULT_PROFILE_NAME


def default_projection_values(today=None):
    """Built-in defaults for a first-time (no saved settings) load."""
    today = today or date.today()
    return {
        "birth_year": today.year - 40,
        "end_year": today.year + 40,
        "retirement_age": 65,
        "return_rate_before_retirement": 7.0,
        "return_rate_after_retirement": 5.0,
        "annual_income": 80000.0,
        "tax_rate": 20.0,
        "inflation_rate": 3.0,
        "spending_before_retirement": 60000.0,
        "spending_after_retirement": 50000.0,
        "social_security_annual_amount": 20000.0,
        "social_security_start_year": today.year + 27,
        "social_security_annual_amount_2": 0.0,
        "social_security_start_year_2": today.year + 27,
        "house_sale_year": today.year + 20,
        "inheritance_amount": 0.0,
        "inheritance_year": today.year + 20,
        "medical_cost_after_retirement": 0.0,
        "medicare_age": 65,
        "withdrawal_tax_rate": 15.0,
        "include_rsu_vesting": True,
        "include_college_tuition": True,
        "include_house_sale": True,
        "include_inheritance": True,
    }


class ProjectionControlsPanel(QWidget):
    updated = Signal()
    profile_selected = Signal(str)
    profile_renamed = Signal(str, str)
    profile_added = Signal(str)

    def __init__(self, parent=None, today=None):
        super().__init__(parent)
        defaults = default_projection_values(today)

        self.profile_combo = QComboBox()
        self.profile_combo.addItem(DEFAULT_PROFILE_NAME)
        self.profile_combo.currentTextChanged.connect(self._on_profile_combo_changed)

        self.profile_name_edit = QLineEdit(DEFAULT_PROFILE_NAME)
        self.profile_name_edit.editingFinished.connect(self._on_profile_name_edited)

        self.add_profile_button = QPushButton("+")
        self.add_profile_button.setToolTip("Add a new profile")
        self.add_profile_button.clicked.connect(self._on_add_profile_clicked)

        self.birth_year_spinbox = year_spinbox(defaults["birth_year"])
        self.end_year_spinbox = year_spinbox(defaults["end_year"])
        self.retirement_age_spinbox = QSpinBox()
        self.retirement_age_spinbox.setRange(1, 120)
        self.retirement_age_spinbox.setValue(defaults["retirement_age"])
        self.starting_investment_value_spinbox = dollar_spinbox(0.0)
        self.starting_investment_value_spinbox.setEnabled(False)
        self.starting_investment_value_spinbox.setToolTip(
            "Derived automatically from your Investment accounts; not editable."
        )

        self.return_rate_before_spinbox = percent_spinbox(defaults["return_rate_before_retirement"])
        self.return_rate_after_spinbox = percent_spinbox(defaults["return_rate_after_retirement"])

        self.annual_income_spinbox = dollar_spinbox(defaults["annual_income"])
        self.tax_rate_spinbox = percent_spinbox(defaults["tax_rate"])
        self.inflation_rate_spinbox = percent_spinbox(defaults["inflation_rate"])
        self.withdrawal_tax_rate_spinbox = percent_spinbox(defaults["withdrawal_tax_rate"])

        self.spending_before_spinbox = dollar_spinbox(defaults["spending_before_retirement"])
        self.spending_after_spinbox = dollar_spinbox(defaults["spending_after_retirement"])

        self.social_security_amount_spinbox = dollar_spinbox(defaults["social_security_annual_amount"])
        self.social_security_start_year_spinbox = year_spinbox(defaults["social_security_start_year"])
        self.social_security_amount_2_spinbox = dollar_spinbox(defaults["social_security_annual_amount_2"])
        self.social_security_start_year_2_spinbox = year_spinbox(defaults["social_security_start_year_2"])

        self.medical_cost_spinbox = dollar_spinbox(defaults["medical_cost_after_retirement"])
        self.medicare_age_spinbox = QSpinBox()
        self.medicare_age_spinbox.setRange(1, 120)
        self.medicare_age_spinbox.setValue(defaults["medicare_age"])

        self.house_account_combo = QComboBox()
        self.house_account_combo.addItem("None", None)
        self.house_sale_year_spinbox = year_spinbox(defaults["house_sale_year"])

        self.inheritance_amount_spinbox = dollar_spinbox(defaults["inheritance_amount"])
        self.inheritance_year_spinbox = year_spinbox(defaults["inheritance_year"])

        self.include_rsu_vesting_checkbox = QCheckBox("Include RSU Vesting Forecast")
        self.include_rsu_vesting_checkbox.setChecked(defaults["include_rsu_vesting"])
        self.include_college_tuition_checkbox = QCheckBox("Include College Tuition Projection")
        self.include_college_tuition_checkbox.setChecked(defaults["include_college_tuition"])
        self.include_house_sale_checkbox = QCheckBox("Include House Sale")
        self.include_house_sale_checkbox.setChecked(defaults["include_house_sale"])
        self.include_inheritance_checkbox = QCheckBox("Include Inheritance")
        self.include_inheritance_checkbox.setChecked(defaults["include_inheritance"])

        self.update_button = QPushButton("Update")
        self.update_button.clicked.connect(self.updated.emit)

        layout = QVBoxLayout(self)

        profile_row = QHBoxLayout()
        profile_row.addWidget(QLabel("Profile:"))
        profile_row.addWidget(self.profile_combo)
        profile_row.addWidget(self.profile_name_edit)
        profile_row.addWidget(self.add_profile_button)
        layout.addLayout(profile_row)

        timeline_form = QFormLayout()
        timeline_form.addRow("Birth year:", self.birth_year_spinbox)
        timeline_form.addRow("Projection end year:", self.end_year_spinbox)
        timeline_form.addRow("Retirement age:", self.retirement_age_spinbox)
        timeline_form.addRow("Starting investment value:", self.starting_investment_value_spinbox)

        returns_form = QFormLayout()
        returns_form.addRow("Return before retirement:", self.return_rate_before_spinbox)
        returns_form.addRow("Return after retirement:", self.return_rate_after_spinbox)

        income_form = QFormLayout()
        income_form.addRow("Annual income:", self.annual_income_spinbox)
        income_form.addRow("Tax rate:", self.tax_rate_spinbox)
        income_form.addRow("Inflation rate:", self.inflation_rate_spinbox)
        income_form.addRow("Investment withdrawal tax rate:", self.withdrawal_tax_rate_spinbox)

        spending_form = QFormLayout()
        spending_form.addRow("Spending before retirement (per year):", self.spending_before_spinbox)
        spending_form.addRow("Spending after retirement (per year):", self.spending_after_spinbox)
        spending_form.addRow("Yearly medical costs (after retirement):", self.medical_cost_spinbox)
        spending_form.addRow("Medicare eligibility age:", self.medicare_age_spinbox)

        ss_form = QFormLayout()
        ss_form.addRow("Social Security annual amount (Person 1):", self.social_security_amount_spinbox)
        ss_form.addRow("Social Security start year (Person 1):", self.social_security_start_year_spinbox)
        ss_form.addRow("Social Security annual amount (Person 2):", self.social_security_amount_2_spinbox)
        ss_form.addRow("Social Security start year (Person 2):", self.social_security_start_year_2_spinbox)

        house_form = QFormLayout()
        house_form.addRow("House account:", self.house_account_combo)
        house_form.addRow("House sale year:", self.house_sale_year_spinbox)

        inheritance_form = QFormLayout()
        inheritance_form.addRow("Inheritance amount (one-time):", self.inheritance_amount_spinbox)
        inheritance_form.addRow("Inheritance year:", self.inheritance_year_spinbox)

        layout.addWidget(QLabel("<b>Include</b>"))
        layout.addWidget(self.include_rsu_vesting_checkbox)
        layout.addWidget(self.include_college_tuition_checkbox)
        layout.addWidget(self.include_house_sale_checkbox)
        layout.addWidget(self.include_inheritance_checkbox)
        layout.addWidget(QLabel("<b>Timeline</b>"))
        layout.addLayout(timeline_form)
        layout.addWidget(QLabel("<b>Investment Returns</b>"))
        layout.addLayout(returns_form)
        layout.addWidget(QLabel("<b>Income &amp; Tax</b>"))
        layout.addLayout(income_form)
        layout.addWidget(QLabel("<b>Spending</b>"))
        layout.addLayout(spending_form)
        layout.addWidget(QLabel("<b>Social Security</b>"))
        layout.addLayout(ss_form)
        layout.addWidget(QLabel("<b>House Sale</b>"))
        layout.addLayout(house_form)
        layout.addWidget(QLabel("<b>Inheritance</b>"))
        layout.addLayout(inheritance_form)
        layout.addWidget(self.update_button)
        layout.addStretch()

    def set_profile_names(self, names, active):
        """names: iterable of profile name strings. active: the one to select."""
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        self.profile_combo.addItems(names)
        index = self.profile_combo.findText(active)
        self.profile_combo.setCurrentIndex(index if index >= 0 else 0)
        self.profile_combo.blockSignals(False)
        self.profile_name_edit.setText(self.profile_combo.currentText())

    def add_profile_name(self, name):
        self.profile_combo.blockSignals(True)
        self.profile_combo.addItem(name)
        self.profile_combo.setCurrentText(name)
        self.profile_combo.blockSignals(False)
        self.profile_name_edit.setText(name)

    def _on_profile_combo_changed(self, name):
        if not name:
            return
        self.profile_name_edit.setText(name)
        self.profile_selected.emit(name)

    def _on_profile_name_edited(self):
        old_name = self.profile_combo.currentText()
        new_name = self.profile_name_edit.text().strip()
        if not new_name or new_name == old_name:
            self.profile_name_edit.setText(old_name)
            return
        existing_names = [self.profile_combo.itemText(i) for i in range(self.profile_combo.count())]
        if new_name in existing_names:
            self.profile_name_edit.setText(old_name)
            return
        index = self.profile_combo.currentIndex()
        self.profile_combo.blockSignals(True)
        self.profile_combo.setItemText(index, new_name)
        self.profile_combo.blockSignals(False)
        self.profile_renamed.emit(old_name, new_name)

    def _on_add_profile_clicked(self):
        name, ok = QInputDialog.getText(self, "New Profile", "Profile name:")
        name = name.strip()
        if not ok or not name:
            return
        existing_names = [self.profile_combo.itemText(i) for i in range(self.profile_combo.count())]
        if name in existing_names:
            return
        self.add_profile_name(name)
        self.profile_added.emit(name)

    def set_house_accounts(self, accounts):
        """accounts: iterable of (account_id, name) pairs for Asset-type accounts."""
        current = self.house_account_combo.currentData()
        self.house_account_combo.blockSignals(True)
        self.house_account_combo.clear()
        self.house_account_combo.addItem("None", None)
        for account_id, name in accounts:
            self.house_account_combo.addItem(name, account_id)
        index = self.house_account_combo.findData(current)
        self.house_account_combo.setCurrentIndex(index if index >= 0 else 0)
        self.house_account_combo.blockSignals(False)

    def values(self):
        return {
            "birth_year": self.birth_year_spinbox.value(),
            "end_year": self.end_year_spinbox.value(),
            "retirement_age": self.retirement_age_spinbox.value(),
            "starting_investment_value": self.starting_investment_value_spinbox.value(),
            "return_rate_before_retirement": self.return_rate_before_spinbox.value(),
            "return_rate_after_retirement": self.return_rate_after_spinbox.value(),
            "annual_income": self.annual_income_spinbox.value(),
            "tax_rate": self.tax_rate_spinbox.value(),
            "inflation_rate": self.inflation_rate_spinbox.value(),
            "withdrawal_tax_rate": self.withdrawal_tax_rate_spinbox.value(),
            "spending_before_retirement": self.spending_before_spinbox.value(),
            "spending_after_retirement": self.spending_after_spinbox.value(),
            "medical_cost_after_retirement": self.medical_cost_spinbox.value(),
            "medicare_age": self.medicare_age_spinbox.value(),
            "social_security_annual_amount": self.social_security_amount_spinbox.value(),
            "social_security_start_year": self.social_security_start_year_spinbox.value(),
            "social_security_annual_amount_2": self.social_security_amount_2_spinbox.value(),
            "social_security_start_year_2": self.social_security_start_year_2_spinbox.value(),
            "house_account_id": self.house_account_combo.currentData(),
            "house_sale_year": self.house_sale_year_spinbox.value(),
            "inheritance_amount": self.inheritance_amount_spinbox.value(),
            "inheritance_year": self.inheritance_year_spinbox.value(),
            "include_rsu_vesting": self.include_rsu_vesting_checkbox.isChecked(),
            "include_college_tuition": self.include_college_tuition_checkbox.isChecked(),
            "include_house_sale": self.include_house_sale_checkbox.isChecked(),
            "include_inheritance": self.include_inheritance_checkbox.isChecked(),
        }

    def set_values(self, values):
        widgets = {
            "birth_year": self.birth_year_spinbox,
            "end_year": self.end_year_spinbox,
            "retirement_age": self.retirement_age_spinbox,
            "starting_investment_value": self.starting_investment_value_spinbox,
            "return_rate_before_retirement": self.return_rate_before_spinbox,
            "return_rate_after_retirement": self.return_rate_after_spinbox,
            "annual_income": self.annual_income_spinbox,
            "tax_rate": self.tax_rate_spinbox,
            "inflation_rate": self.inflation_rate_spinbox,
            "withdrawal_tax_rate": self.withdrawal_tax_rate_spinbox,
            "spending_before_retirement": self.spending_before_spinbox,
            "spending_after_retirement": self.spending_after_spinbox,
            "medical_cost_after_retirement": self.medical_cost_spinbox,
            "medicare_age": self.medicare_age_spinbox,
            "social_security_annual_amount": self.social_security_amount_spinbox,
            "social_security_start_year": self.social_security_start_year_spinbox,
            "social_security_annual_amount_2": self.social_security_amount_2_spinbox,
            "social_security_start_year_2": self.social_security_start_year_2_spinbox,
            "house_sale_year": self.house_sale_year_spinbox,
            "inheritance_amount": self.inheritance_amount_spinbox,
            "inheritance_year": self.inheritance_year_spinbox,
        }
        for key, widget in widgets.items():
            if key not in values:
                continue
            try:
                widget.setValue(values[key])
            except TypeError:
                continue
        if "house_account_id" in values:
            index = self.house_account_combo.findData(values["house_account_id"])
            self.house_account_combo.setCurrentIndex(index if index >= 0 else 0)
        if "include_rsu_vesting" in values:
            self.include_rsu_vesting_checkbox.setChecked(bool(values["include_rsu_vesting"]))
        if "include_college_tuition" in values:
            self.include_college_tuition_checkbox.setChecked(bool(values["include_college_tuition"]))
        if "include_house_sale" in values:
            self.include_house_sale_checkbox.setChecked(bool(values["include_house_sale"]))
        if "include_inheritance" in values:
            self.include_inheritance_checkbox.setChecked(bool(values["include_inheritance"]))
