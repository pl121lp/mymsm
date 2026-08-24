"""Shared spinbox factories for report control panels (Net Worth
Projection, College Tuition Projection): year, percentage, and dollar
inputs with consistent ranges and formatting.
"""

from PySide6.QtWidgets import QDoubleSpinBox, QSpinBox


def year_spinbox(value):
    spinbox = QSpinBox()
    spinbox.setRange(1900, 2200)
    spinbox.setValue(value)
    return spinbox


def percent_spinbox(value):
    spinbox = QDoubleSpinBox()
    spinbox.setRange(-20.0, 100.0)
    spinbox.setDecimals(2)
    spinbox.setSuffix("%")
    spinbox.setValue(value)
    return spinbox


def dollar_spinbox(value):
    spinbox = QDoubleSpinBox()
    spinbox.setRange(0.0, 100_000_000.0)
    spinbox.setDecimals(2)
    spinbox.setSingleStep(1000.0)
    spinbox.setPrefix("$")
    spinbox.setValue(value)
    return spinbox
