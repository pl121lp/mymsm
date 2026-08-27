from datetime import date
from decimal import Decimal

from PySide6.QtCore import Qt

import charts
from charts import build_bar_chart, build_line_chart, build_pie_chart, build_stacked_area_chart


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


def test_build_bar_chart_hover_shows_date_and_value(qapp, monkeypatch):
    shown = []
    monkeypatch.setattr(charts.QToolTip, "showText", lambda pos, text: shown.append(text))

    chart = build_bar_chart("Net Worth Over Time (USD)", ["2024-07-01", "2024-09-01"], [1234.5, 6789.25])
    series = chart.series()[0]
    bar_set = series.barSets()[0]

    series.hovered.emit(True, 0, bar_set)
    assert shown == ["2024-07-01: 1,234.50"]

    series.hovered.emit(True, 1, bar_set)
    assert shown == ["2024-07-01: 1,234.50", "2024-09-01: 6,789.25"]


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


def _bands():
    bottom = [(date(2024, 1, 1), Decimal("100")), (date(2024, 2, 1), Decimal("100"))]
    top = [(date(2024, 1, 1), Decimal("50")), (date(2024, 2, 1), Decimal("150"))]
    return [("Bottom", bottom, "#ADD8E6"), ("Top", top, "#FFCC80")]


def test_build_stacked_area_chart_creates_one_area_series_per_band(qapp):
    chart = build_stacked_area_chart("Title", _bands())

    assert [s.name() for s in chart.series()] == ["Bottom", "Top"]


def test_build_stacked_area_chart_stacks_bands_cumulatively(qapp):
    chart = build_stacked_area_chart("Title", _bands())

    bottom_series, top_series = chart.series()

    assert [point.y() for point in bottom_series.lowerSeries().points()] == [0.0, 0.0]
    assert [point.y() for point in bottom_series.upperSeries().points()] == [100.0, 100.0]
    assert [point.y() for point in top_series.lowerSeries().points()] == [100.0, 100.0]
    assert [point.y() for point in top_series.upperSeries().points()] == [150.0, 250.0]


def test_build_stacked_area_chart_mark_zero_extends_range_to_include_zero(qapp):
    negative_bottom = [(date(2024, 1, 1), Decimal("-10")), (date(2024, 2, 1), Decimal("-10"))]
    chart = build_stacked_area_chart("Title", [("Bottom", negative_bottom, "#ADD8E6")], mark_zero=True)

    axis_y = chart.axes(Qt.Vertical)[0]
    assert axis_y.max() == 0.0
