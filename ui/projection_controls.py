"""Controls panel for the Net Worth Projection report: birth year,
retirement age, investment returns, income/spending, tax, inflation, and
Social Security inputs, laid out in labeled sections with an Update
button.
"""

from datetime import date

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFormLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)


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
    }


def _year_spinbox(value):
    spinbox = QSpinBox()
    spinbox.setRange(1900, 2200)
    spinbox.setValue(value)
    return spinbox


def _percent_spinbox(value):
    spinbox = QDoubleSpinBox()
    spinbox.setRange(-20.0, 100.0)
    spinbox.setDecimals(2)
    spinbox.setSuffix("%")
    spinbox.setValue(value)
    return spinbox


def _dollar_spinbox(value):
    spinbox = QDoubleSpinBox()
    spinbox.setRange(0.0, 100_000_000.0)
    spinbox.setDecimals(2)
    spinbox.setSingleStep(1000.0)
    spinbox.setPrefix("$")
    spinbox.setValue(value)
    return spinbox


class ProjectionControlsPanel(QWidget):
    updated = Signal()

    def __init__(self, parent=None, today=None):
        super().__init__(parent)
        defaults = default_projection_values(today)

        self.birth_year_spinbox = _year_spinbox(defaults["birth_year"])
        self.end_year_spinbox = _year_spinbox(defaults["end_year"])
        self.retirement_age_spinbox = QSpinBox()
        self.retirement_age_spinbox.setRange(1, 120)
        self.retirement_age_spinbox.setValue(defaults["retirement_age"])
        self.starting_investment_value_spinbox = _dollar_spinbox(0.0)

        self.return_rate_before_spinbox = _percent_spinbox(defaults["return_rate_before_retirement"])
        self.return_rate_after_spinbox = _percent_spinbox(defaults["return_rate_after_retirement"])

        self.annual_income_spinbox = _dollar_spinbox(defaults["annual_income"])
        self.tax_rate_spinbox = _percent_spinbox(defaults["tax_rate"])
        self.inflation_rate_spinbox = _percent_spinbox(defaults["inflation_rate"])

        self.spending_before_spinbox = _dollar_spinbox(defaults["spending_before_retirement"])
        self.spending_after_spinbox = _dollar_spinbox(defaults["spending_after_retirement"])

        self.social_security_amount_spinbox = _dollar_spinbox(defaults["social_security_annual_amount"])
        self.social_security_start_year_spinbox = _year_spinbox(defaults["social_security_start_year"])

        self.update_button = QPushButton("Update")
        self.update_button.clicked.connect(self.updated.emit)

        layout = QVBoxLayout(self)

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

        spending_form = QFormLayout()
        spending_form.addRow("Spending before retirement:", self.spending_before_spinbox)
        spending_form.addRow("Spending after retirement:", self.spending_after_spinbox)

        ss_form = QFormLayout()
        ss_form.addRow("Social Security annual amount:", self.social_security_amount_spinbox)
        ss_form.addRow("Social Security start year:", self.social_security_start_year_spinbox)

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
        layout.addWidget(self.update_button)
        layout.addStretch()

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
            "spending_before_retirement": self.spending_before_spinbox.value(),
            "spending_after_retirement": self.spending_after_spinbox.value(),
            "social_security_annual_amount": self.social_security_amount_spinbox.value(),
            "social_security_start_year": self.social_security_start_year_spinbox.value(),
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
            "spending_before_retirement": self.spending_before_spinbox,
            "spending_after_retirement": self.spending_after_spinbox,
            "social_security_annual_amount": self.social_security_amount_spinbox,
            "social_security_start_year": self.social_security_start_year_spinbox,
        }
        for key, widget in widgets.items():
            if key in values:
                widget.setValue(values[key])
