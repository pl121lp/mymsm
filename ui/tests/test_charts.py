from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt

from charts import build_line_chart, build_pie_chart


def test_build_pie_chart_creates_one_slice_per_category(qapp):
    chart = build_pie_chart(
        "Spending by Category",
        [("Utilities", Decimal("75.00")), ("Groceries", Decimal("72.30"))],
    )

    assert len(chart.series()) == 1
    series = chart.series()[0]
    slices = series.slices()
    assert len(slices) == 2
    assert slices[0].label() == "Utilities"
    assert slices[0].value() == 75.00
    assert slices[1].label() == "Groceries"
    assert slices[1].value() == 72.30


def _points():
    return [(date(2024, 1, 1), Decimal("100")), (date(2024, 2, 1), Decimal("200"))]


def test_build_line_chart_by_default_does_not_force_zero_into_range(qapp):
    chart = build_line_chart("Title", [("Series", _points())])

    axis_y = chart.axes(Qt.Vertical)[0]
    assert axis_y.min() == 100.0
    assert len(chart.series()) == 1


def test_build_line_chart_mark_zero_extends_range_to_include_zero(qapp):
    chart = build_line_chart("Title", [("Series", _points())], mark_zero=True)

    axis_y = chart.axes(Qt.Vertical)[0]
    assert axis_y.min() == 0.0
    assert axis_y.max() == 200.0


def test_build_line_chart_mark_zero_adds_a_hidden_zero_reference_series(qapp):
    chart = build_line_chart("Title", [("Series", _points())], mark_zero=True)

    assert len(chart.series()) == 2
    zero_series = chart.series()[-1]
    assert all(point.y() == 0.0 for point in zero_series.points())
    markers = chart.legend().markers(zero_series)
    assert markers and markers[0].isVisible() is False
